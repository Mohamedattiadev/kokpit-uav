# 07 — MAVLINK KÖPRÜSÜ (Jetson ↔ Pixhawk ArduCopter)

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `Promptlar/03_jetson_mission_computer.md`

## Görev
Jetson ile Pixhawk 2.4.8 (ArduCopter firmware) arasında MAVLink iletişim katmanı. Yüksek seviye API'ler: `arm`, `takeoff`, `goto`, `set_velocity`, `set_servo`, `set_mode`, `rtl`, `land`. Heartbeat monitoring, failsafe tetikleyici, mode değişim event'leri.

## Açılışta Executor'a Sor (zorunlu)

1. **Kütüphane**: `pymavlink` (tavsiye — düşük seviye, esnek) mi, `dronekit-python` (yüksek seviye ama bakımı durdu) mi, `mavsdk-python` (MAVSDK, modern ama PX4 odaklı) mı?
2. **Fiziksel bağlantı**: USB (`/dev/ttyACM0` @ 115200) (tavsiye, basit) mi, TELEM2 UART (`/dev/ttyTHS1` @ 921600) (üretim için daha güvenilir) mı?
3. **MAVLink protokol versiyonu**: v2 (tavsiye — ArduCopter 4.x default) mi, v1 mi?
4. **System/Component ID**: Jetson SYSID=1 COMPID=191 (MAV_COMP_ID_ONBOARD_COMPUTER, tavsiye). Onay?
5. **GUIDED mode vs offboard scripting**: Visual servoing için GUIDED + `SET_POSITION_TARGET_LOCAL_NED` (tavsiye). Onay?
6. **Heartbeat frekansı**: 1 Hz çift yönlü (standart). Onay?
7. **Telemetri stream rate'leri**: `ATTITUDE@10Hz, GLOBAL_POSITION_INT@5Hz, BATTERY_STATUS@1Hz, RANGEFINDER@5Hz` — onay?

## Mimari

```
jetson/mission_computer/src/kokpit/mavlink_bridge.py
jetson/mission_computer/src/kokpit/ardupilot_params/
└── kokpit.param          # ArduCopter parametre seti
```

## API (yüksek seviye)

```python
class MAVBridge:
    async def connect(self) -> None: ...
    async def wait_heartbeat(self, timeout: float = 10.0) -> None: ...

    # Komutlar
    async def set_mode(self, mode: str) -> bool: ...     # GUIDED, AUTO, RTL, LAND, LOITER
    async def arm(self) -> bool: ...
    async def disarm(self, force: bool = False) -> bool: ...
    async def takeoff(self, alt_m: float) -> bool: ...
    async def goto(self, lat: float, lon: float, alt_m: float) -> None: ...
    async def send_velocity_target(
        self, vx: float, vy: float, vz: float, yaw_rad: float = 0
    ) -> None: ...
    async def set_servo(self, channel: int, pwm: int) -> bool: ...
    async def send_distance_sensor(self, ...) -> None: ...  # modül 06 kullanır
    async def rtl(self) -> bool: ...
    async def land(self) -> bool: ...

    # Telemetri stream
    async def telemetry_stream(self) -> AsyncIterator[Telemetry]: ...

    # Failsafe
    on_failsafe: Callable[[FailsafeKind], None]  # callback
```

## Implementasyon Detayları

### Bağlantı
```python
from pymavlink import mavutil

self.conn = mavutil.mavlink_connection(
    cfg.mavlink.url,
    source_system=1,
    source_component=mavlink.MAV_COMP_ID_ONBOARD_COMPUTER,
)
```

### Heartbeat Task
```python
async def _heartbeat_tx_loop(self):
    while True:
        self.conn.mav.heartbeat_send(
            mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
            mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0,
        )
        await asyncio.sleep(1.0)

async def _heartbeat_rx_monitor(self):
    while True:
        if time.monotonic() - self.last_hb_rx > 3.0:
            self.on_failsafe(FailsafeKind.LINK_LOST)
        await asyncio.sleep(0.5)
```

### `send_velocity_target` (visual servoing için kritik)
```python
async def send_velocity_target(self, vx, vy, vz, yaw_rad=0):
    type_mask = (
        mavlink.POSITION_TARGET_TYPEMASK_X_IGNORE
        | mavlink.POSITION_TARGET_TYPEMASK_Y_IGNORE
        | mavlink.POSITION_TARGET_TYPEMASK_Z_IGNORE
        | mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
        | mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
        | mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
        | mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
    )
    self.conn.mav.set_position_target_local_ned_send(
        0, 1, 1,
        mavlink.MAV_FRAME_BODY_OFFSET_NED,
        type_mask,
        0, 0, 0,     # pos ignored
        vx, vy, vz,
        0, 0, 0,
        yaw_rad, 0,
    )
```

### `set_servo` (paket bırakma için)
```python
async def set_servo(self, channel: int, pwm: int) -> bool:
    return await self._cmd_long(
        mavlink.MAV_CMD_DO_SET_SERVO,
        param1=channel,  # AUX out kanal numarası (9-14)
        param2=pwm,      # 1000-2000
    )
```

### Mesaj Filtreleme & Stream
- `recv_match()` async wrap (`asyncio.to_thread` veya custom selector)
- Tip bazlı dispatch → `EventBus`'a publish

## ArduCopter Parametreleri (`kokpit.param`)

Kritik paramlar (executor netleştirsin):
```
SYSID_MYGCS = 1            # Jetson Failsafe için tanır
SR1_POSITION = 5           # USB stream rate
SR1_EXTRA1 = 10
SR1_EXTRA3 = 1
COMPANION_ID = 191
GPS_TYPE = 1
EKF3_ENABLE = 1
EK3_GPS_TYPE = 0
EK2_ENABLE = 0
FS_GCS_ENABLE = 1          # GCS link lost = failsafe
FS_GCS_TIMEOUT = 3
RTL_ALT = 3000             # 30 m
ARMING_CHECK = 1
BRD_SAFETY_DEFLT = 0
RC8_OPTION = 0
SERVO9_FUNCTION = 0        # Kullanılacak servo paket için (RCx out)
SERVO9_MIN = 1000
SERVO9_MAX = 2000
SERVO9_TRIM = 1000         # idle = kapalı
```

## Failsafe Mantığı

```python
class FailsafeKind(Enum):
    LINK_LOST = "link_lost"          # MAVLink heartbeat timeout
    BATTERY_LOW = "battery_low"      # < cfg.battery_failsafe_pct
    GPS_LOST = "gps_lost"            # GPS fix kaybı > 5 sn
    GEOFENCE = "geofence"
    USER_ABORT = "user_abort"
```
Callback state machine'i tetikler (modül 08 dinler).

## Testler
- `test_mavlink_bridge.py`: SITL'e bağlan, ARM, TAKEOFF, GOTO, RTL, DISARM full sequence
- `test_failsafe.py`: heartbeat kesintisi → failsafe event
- `test_servo.py`: AUX9 PWM 1000→2000 doğrulama (SITL logunda)
- `test_velocity_target.py`: 1 sn vx=1 → 1m ileri (SITL)

## Kabul Kriterleri
- SITL ile full görev döngüsü (arm → takeoff → goto → land → disarm) ≥ 10/10 başarı
- Komut → ACK gecikmesi < 100 ms (USB)
- 1 saat sürekli bağlantı, drop yok
- Heartbeat kesilirse 3 sn içinde failsafe event

## GÜÇLENDİRMELER (AUDIT)

### G1. Geofence
```python
async def setup_geofence(self, polygon: list[tuple[float, float]], alt_max_m: int = 50):
    # FENCE_TOTAL set, polygon points yükle, FENCE_ENABLE=1
    ...
```
Paramlar: `FENCE_ENABLE=1, FENCE_TYPE=7 (alt+circle+polygon), FENCE_ALT_MAX=50, FENCE_RADIUS=200, FENCE_ACTION=1 (RTL)`. Polygon yarışma alanı GPS köşelerinden yüklenir.

### G2. Battery Voltage Failsafe (SOC% güvenilmez)
Param:
```
BATT_LOW_VOLT = 22.0    # 6S için (3.67V/cell)
BATT_CRT_VOLT = 21.0    # (3.50V/cell)
BATT_FS_LOW_ACT = 2     # RTL
BATT_FS_CRT_ACT = 1     # LAND
```

### G3. RC Failsafe + Pilot Priority (KRİTİK GÜVENLİK)
Pilot kumanda her zaman önceliklidir. Jetson **asla** `RC_OVERRIDE` göndermez. Pilot moda alırsa Jetson read-only.
- `FS_THR_ENABLE=1, FS_THR_VALUE=950` (RC kayıp → RTL)
- Pilot Manual moda alırsa state machine `MissionPhase.PILOT_OVERRIDE`'a geçer

### G4. `send_landing_target` (PRECLAND için)
Modül 05 G2 ile bağlantılı. API ekle:
```python
async def send_landing_target(self, angle_x, angle_y, distance, size_x=0, size_y=0): ...
```

### G5. Force Disarm + Motor Interlock
```python
async def force_disarm(self) -> bool:
    return await self._cmd_long(
        MAV_CMD_COMPONENT_ARM_DISARM, param1=0, param2=21196  # force magic
    )
```
Crash detection (modül 08) bunu çağırır.

### G6. Stream Rate Setup
Boot'ta `REQUEST_DATA_STREAM` veya `MESSAGE_INTERVAL`:
```
ATTITUDE: 20 Hz
GLOBAL_POSITION_INT: 5 Hz
RANGEFINDER: 10 Hz
BATTERY_STATUS: 1 Hz
RAW_IMU: 20 Hz (crash detection için)
HOME_POSITION: 0.5 Hz
SYSTEM_TIME: 0.2 Hz (Jetson time sync için)
```

### G7. TELEM2 vs USB
USB 115200 yetersiz olabilir (`SET_POSITION_TARGET` 20 Hz × ~50 byte + diğer stream'ler). Üretimde TELEM2 921600 tercih. Param: `SERIAL2_PROTOCOL=2, SERIAL2_BAUD=921`.

## Verme
- Çalışan `mavlink_bridge.py`
- `kokpit.param` (MissionPlanner'a yüklenebilir)
- SITL test runner script
- README: ArduCopter SITL kurulum, parametre yükleme, troubleshooting
