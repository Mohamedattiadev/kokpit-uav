# 11 — SITL + GAZEBO SİMÜLASYON ORTAMI

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. Tüm 03–09 modülleri (entegrasyon hedefleri)

## Görev
Tam görev döngüsünü gerçek donanım olmadan koşturabileceğimiz bir simülasyon ortamı kur. ArduCopter SITL + Gazebo dünyası + sahte LoRa (UDP loopback) + sahte kamera (video dosyası veya Gazebo kamera plugin) + sahte lidar.

## Açılışta Executor'a Sor (zorunlu)

1. **Simülatör**: Gazebo Garden/Harmonic (tavsiye — modern, ArduPilot resmi destek) mi, Gazebo Classic 11 mi, AirSim mi?
2. **Host OS**: Ubuntu 22.04 native (tavsiye) mi, Docker compose stack mi (taşınabilir)?
3. **Sahte kamera**: Önceden çekilmiş video dosyası (deterministik, tavsiye) mı, Gazebo kamera plugin (gerçekçi ama heavy) mı?
4. **Sahte ArUco**: Gazebo dünyasında texture'lı ped (tavsiye) mi, kamera frame'ine post-process overlay mi?
5. **Sahte LoRa**: UDP loopback (tavsiye, basit) mi, ZeroMQ pub/sub mu?
6. **CI**: GitHub Actions'ta headless çalışsın mı (tavsiye — regression catch)?

## Yapı

```
sim/simulation/
├── docker-compose.yml         # opsiyonel
├── start_sitl.sh              # ArduCopter SITL launch
├── start_gazebo.sh            # Gazebo + world
├── start_fake_lora.py         # UDP loopback server
├── start_fake_camera.py       # video → /dev/video10 (v4l2loopback)
├── worlds/
│   └── kokpit_arena.world     # Gazebo world: ped + ArUco texture
├── models/
│   ├── delivery_pad/
│   └── iris_with_camera/
├── scenarios/
│   ├── happy_path.py
│   ├── marker_lost.py
│   ├── face_mismatch.py
│   ├── link_lost.py
│   └── battery_low.py
└── README.md
```

## Bileşenler

### 1. ArduCopter SITL
```bash
./Tools/autotest/sim_vehicle.py -v ArduCopter \
  --console --map \
  --custom-location=39.925533,32.866287,938,0  # Ankara
```
- MAVLink endpoint: `udp:127.0.0.1:14550` → MissionPlanner, `udp:127.0.0.1:14551` → Jetson mission computer

### 2. Gazebo Dünyası
- `iris` quadcopter modeli + downward camera + lidar plugin
- `delivery_pad` modeli: ArUco marker texture (DICT_4X4_50, ID 42)
- Ankara koordinatlarında flat ground

### 3. Sahte LoRa Server
```python
# start_fake_lora.py
# ESP32 yerine UDP üzerinden TRIGGER paketi inject eder
# Mission computer'ın lora_rx'i konfigden /dev/null yerine udp socket okur
```

### 4. Sahte Kamera (gerçek video oynatma)
- v4l2loopback ile sanal `/dev/video10`
- `ffmpeg -re -stream_loop -1 -i sample.mp4 -f v4l2 /dev/video10`
- Mission computer kamerayı `/dev/video10`'dan açar

### 5. Scenario Runner
```python
# scenarios/happy_path.py
async def main():
    sitl = SITL.start()
    fake_lora = FakeLoRa.start()
    mc = MissionComputer.start(config="sim_config.yaml")
    await asyncio.sleep(5)
    fake_lora.send_trigger(lat=39.925, lon=32.867, jpeg=load("alice.jpg"))
    await mc.wait_for_phase(MissionPhase.DONE, timeout=300)
    assert mc.state.face_verified
    assert mc.state.position_near_home(threshold_m=2)
```

## CI Integration

```yaml
# .github/workflows/sitl.yml
on: [push, pull_request]
jobs:
  sitl:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - run: sudo apt install -y gazebo libgz-sim7-dev v4l2loopback-dkms
      - run: ./sim/simulation/install_ardupilot.sh
      - run: pytest sim/simulation/scenarios/ --timeout=600
```

## Testler / Senaryolar
1. **happy_path**: Tetik → kalkış → uçuş → marker → yüz onay → teslim → RTL → DONE
2. **marker_lost**: Marker hiç gözükmez → sarmal → 30sn → RTL
3. **face_mismatch**: Yanlış yüz → 20sn → RTL paket teslim ETMEDEN
4. **link_lost**: SITL'e heartbeat kes → 3sn → failsafe → RTL
5. **battery_low**: SITL `SIM_BATT_VOLTAGE` düşür → %20 → RTL
6. **gps_lost**: SITL `SIM_GPS_DISABLE=1` 5sn → EKF kestirim → recover veya LOITER

## Kabul Kriterleri
- 6 senaryo CI'da yeşil
- Her senaryo < 5 dakika
- Tüm modüller (03-09) SITL ortamında end-to-end çalışır

## Verme
- Çalışan `start_sitl.sh` + `start_gazebo.sh` + `start_fake_lora.py`
- `sim/simulation/README.md`: kurulum, çalıştırma, debug
- 6 scenario testi
- CI workflow YAML
- Demo videosu (happy_path SITL kayıt) opsiyonel
