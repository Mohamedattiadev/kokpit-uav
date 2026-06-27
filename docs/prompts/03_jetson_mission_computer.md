# 03 — JETSON GÖREV BİLGİSAYARI (Mission Computer Ana İskelet)

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `shared/protocol/packet_spec.md`

## Görev
NVIDIA Jetson Orin Nano üzerinde çalışacak görev bilgisayarı ana iskeletini kur. Tek bir `asyncio` event loop, paylaşılan `MissionState`, modüller arası queue/pub-sub. Tüm alt modüller (LoRa RX, MAVLink bridge, ArUco, face, sensor fusion, state machine) bu iskeletin altına plug edilecek.

> **Bu modül "ana çatı". İçindeki her alt modülün KENDİ ayrı prompt'u var (04-09). Bu prompt orchestration ve LoRa RX'ten sorumlu.**

## Açılışta Executor'a Sor (zorunlu)

1. **Dil/runtime**: Python 3.10 + asyncio (tavsiye) mi, C++ + ROS2 Humble mı? *(Tavsiye: Python — geliştirme hızı, TensorRT Python API olgun, MAVLink/`pymavlink` standart)*
2. **Paket yöneticisi**: `uv` (tavsiye, hızlı) mi, `poetry` mi, `pip + venv` mi?
3. **JetPack sürümü**: JetPack 6.x (L4T r36, Ubuntu 22.04, CUDA 12.x) — onay?
4. **Logging**: `structlog` + JSON (tavsiye, GCS'e besleyebiliriz) mi, stdlib `logging` mi?
5. **Process mimarisi**: Tek monolitik process (tavsiye, asyncio yeterli) mi, multi-process (`multiprocessing`) mi?
6. **Hot reload geliştirme için**: `watchdog` ile auto-restart ister misin?

## Mimari

```
jetson/mission_computer/
├── pyproject.toml
├── src/kokpit/
│   ├── __init__.py
│   ├── main.py                  # entrypoint, asyncio.run
│   ├── config.py                # pydantic settings (env + yaml)
│   ├── state.py                 # MissionState dataclass + EventBus
│   ├── lora_rx.py               # LoRa UART → packet decode → event bus
│   ├── mavlink_bridge.py        # modül 07
│   ├── aruco_servoing.py        # modül 05
│   ├── face_recognition/        # modül 04 (alt paket)
│   ├── sensor_fusion.py         # modül 06
│   ├── servo_release.py         # modül 09
│   ├── state_machine.py         # modül 08
│   └── telemetry_tx.py          # İHA→yer LoRa telemetri
├── tests/
├── configs/
│   └── default.yaml
└── README.md
```

## Ana Bileşenler (BU prompt'un kapsamı)

### 1. `MissionState` (paylaşılan state)
```python
@dataclass
class MissionState:
    phase: MissionPhase = MissionPhase.IDLE
    target_lat: float | None = None
    target_lon: float | None = None
    target_alt: float | None = None
    ref_face_jpeg: bytes | None = None
    current_pos: GPSFix | None = None
    battery_pct: float = 100.0
    marker_locked: bool = False
    face_verified: bool = False
    abort_reason: str | None = None
    last_heartbeat: float = 0.0
```
`MissionPhase` enum: `IDLE, ARMED, TAKEOFF, EN_ROUTE, SEARCHING, APPROACHING, VERIFYING, DELIVERING, RTL, LANDING, DONE, ABORTED`.

### 2. `EventBus` (asyncio pub/sub)
- `publish(topic, payload)`, `subscribe(topic) -> AsyncIterator`
- Topic'ler: `lora.trigger`, `lora.abort`, `mavlink.heartbeat`, `aruco.detection`, `face.result`, `servo.released`, `state.transition`

### 3. `lora_rx.py` (BU modülde tam impl)
- UART (`/dev/ttyTHS1` veya `/dev/ttyUSB0`, 9600 baud) async serial read (`pyserial-asyncio`)
- Byte stream → frame sync (magic byte 0x4B 0x50)
- Chunk reassembly buffer (timeout 5 s)
- `shared/protocol/packet.py` ile decrypt + parse
- Sequence number replay protection (LRU set, son 256 seq)
- Decode'ed event → `EventBus.publish("lora.trigger", payload)`
- Ardından `MSG_ACK` geri gönder (telemetry_tx üzerinden)

### 4. `telemetry_tx.py`
- 1 Hz `MissionState` snapshot → TELEMETRY paketi → LoRa UART TX
- ACK paketleri buradan gönderilir

### 5. `main.py`
- Config yükle, log init
- Donanım var mı kontrol et (UART, MAVLink USB, kamera CSI, lidar UART)
- `asyncio.gather` ile tüm modülleri başlat
- SIGTERM/SIGINT → graceful shutdown (MAVLink RTL → disarm bekle)

### 6. `config.py`
```yaml
# configs/default.yaml
lora:
  port: /dev/ttyTHS1
  baud: 9600
  key_path: ~/.config/kokpit/lora.key
mavlink:
  url: serial:///dev/ttyACM0:57600
  system_id: 255
camera:
  device: /dev/video0
  width: 1280
  height: 720
  fps: 30
lidar:
  port: /dev/ttyTHS2
  baud: 115200
mission:
  takeoff_alt_m: 10
  approach_alt_m: 3
  delivery_alt_m: 1.5
  max_navigation_drift_m: 0.8
  face_match_threshold: 0.90
  marker_search_radius_m: 5
  battery_failsafe_pct: 25
```

## Bağımlılıklar (tavsiye)

```toml
[project]
dependencies = [
  "pyserial-asyncio>=0.6",
  "pymavlink>=2.4",
  "opencv-python>=4.10",
  "numpy>=1.26",
  "cryptography>=42",
  "pydantic>=2.6",
  "pydantic-settings>=2.2",
  "structlog>=24.1",
  "pyyaml>=6.0",
  "uvloop>=0.19",  # asyncio hız
]
[project.optional-dependencies]
ml = ["torch", "torchvision", "tensorrt", "pycuda"]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "ruff", "mypy"]
```

## Testler
- `test_state.py`: state transition guard'ları
- `test_event_bus.py`: pub/sub asyncio
- `test_lora_rx.py`: mock UART → fake packet → event bus
- `test_telemetry_tx.py`: state snapshot → byte array
- `test_main_smoke.py`: 5 saniyelik mock run, hata yok

## Kabul Kriterleri
- Cold boot → `lora_rx` dinleme başlama < 3 saniye
- LoRa packet RX → MAVLink waypoint TX gecikme < 200 ms (benchmark)
- 30 dakika idle çalışma, hafıza < 500 MB stable
- SIGINT → RTL komutu → 5 saniye içinde temiz çıkış

## GÜÇLENDİRMELER (AUDIT)

### G1. Pre-arm Checker (`prearm.py`)
ARM komutu öncesi tüm sensör health doğrula:
```python
async def prearm_check(state, mav, lora_rx, face, lidar) -> tuple[bool, list[str]]:
    failures = []
    if (await mav.get_gps_fix()).sat_count < 10: failures.append("gps<10sat")
    if not lidar.healthy(): failures.append("lidar_unhealthy")
    if not face.engines_loaded: failures.append("trt_engines_not_loaded")
    if time.monotonic() - mav.last_hb > 2: failures.append("mavlink_hb_stale")
    if not lora_rx.session_ok: failures.append("lora_no_boot_beacon")
    if state.ref_embedding is None: failures.append("no_ref_face")
    return (len(failures) == 0, failures)
```
state machine `_begin_mission` içinde çağırır, fail → IDLE'da kal + UI'da neden göster.

### G2. Time Sync (`time_sync.py`)
Pixhawk `SYSTEM_TIME` mesajı 0.2 Hz → Jetson sistem saatini slew:
```python
async def time_sync_loop(mav):
    async for msg in mav.recv("SYSTEM_TIME"):
        unix_us = msg.time_unix_usec
        if unix_us > 0:
            os.system(f"date -u -s @{unix_us / 1e6:.6f}")  # veya adjtimex
```
Tüm `structlog` loglar `ts_unix_us`.

### G3. Log Download Otomasyonu
Görev sonu Jetson Pixhawk dataflash log indirir, JSONL ile merge:
```python
async def post_mission_collect(mav, run_id):
    log_list = await mav.log_request_list()
    latest = max(log_list, key=lambda x: x.time_utc)
    bin_path = await mav.log_download(latest.id, f"runs/{run_id}/dataflash.bin")
    # JSONL Jetson logları zaten runs/{run_id}/jetson.jsonl
    merge_logs(bin_path, f"runs/{run_id}/jetson.jsonl", f"runs/{run_id}/merged.csv")
```

### G4. Watchdog (systemd + uygulama içi)
- `systemd/kokpit-mc.service`: `Restart=on-failure RestartSec=3 WatchdogSec=15`
- `main.py`: 5 sn'de bir `sd_notify("WATCHDOG=1")` (systemd-python veya `sdnotify` paketi)

### G5. Versiyon Lock
`uv lock` veya `poetry.lock` commit edilir. `.python-version = 3.10.13`. JetPack uyumluluğu README'de belirtilir.

### G6. TRT Engine Versiyon Cache
Engine dosya adı: `{model}_{trt_version}_{jetpack_version}_{precision}.engine`. Cache miss → rebuild.

## Verme
- Çalışan `pyproject.toml` projesi
- Diğer modüllerin (04-09) plug edebileceği stub'lar (NotImplementedError)
- `make run`, `make test`, `make lint` Makefile
- README: Jetson kurulum (CUDA, TensorRT, OpenCV), `systemd` service dosyası
