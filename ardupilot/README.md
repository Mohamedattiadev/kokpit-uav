# ardupilot/ — Pixhawk Parametre Setleri

Bu klasör Pixhawk 2.4.8 (ArduCopter 4.5+) için `.param` dosyalarını barındırır. MissionPlanner veya QGroundControl üzerinden "Full Parameter List → Load from file" ile yüklenir.

## Yüklenmesi Beklenen Dosyalar (henüz commit edilmedi — `docs/PLAN.md` P2 görevi)

| Dosya | İçerik |
|---|---|
| `kokpit_baseline.param` | Frame, motor, ESC, RC, EKF3 baseline |
| `kokpit_companion.param` | TELEM2 / SERIAL2 Jetson bağlantısı (921600 baud, MAVLink 2) |
| `kokpit_precland.param` | PRECLAND yerleşik hassas iniş (`PLND_ENABLED=1`, `PLND_TYPE=1` MAVLink, `PLND_EST_TYPE=1` Kalman) |
| `kokpit_lidar.param` | Benewake TFS20 (`RNGFND1_TYPE=10` MAVLink, `RNGFND1_ORIENT=25` down, `EK3_RNG_USE_HGT=70`, `EK3_SRC1_POSZ=2`) |
| `kokpit_servo.param` | AUX1/SERVO9 paket bırakma (`SERVO9_FUNCTION=0`, `SERVO9_MIN=1000`, `SERVO9_MAX=2000`, `SERVO9_TRIM=1000` failsafe kapalı) |
| `kokpit_failsafe.param` | Batarya, link, RC, GPS failsafe (`BATT_LOW_VOLT=22.0`, `BATT_CRT_VOLT=21.0`, `BATT_FS_LOW_ACT=2`, `BATT_FS_CRT_ACT=1`, `FS_THR_ENABLE=1`, `FS_GCS_ENABLE=1`) |
| `kokpit_geofence.param` | `FENCE_ENABLE=1`, `FENCE_TYPE=7`, `FENCE_RADIUS=200`, `FENCE_ALT_MAX=50`, `FENCE_ACTION=1` (RTL) — polygon ayrıca `.poly` ile yüklenir |
| `kokpit_arena.poly` | Yarışma alanı GPS polygon (4–6 nokta, sahaya göre) |

## Kalibrasyon Sırası (her parametre yüklemesinden sonra)
1. Accelerometer kalibrasyon (6 yüz)
2. Kompas kalibrasyon (dönerek)
3. Radyo kalibrasyon
4. ESC kalibrasyon
5. Level horizon
6. Yer testinde motor sırası + dönüş yönü doğrula

## Ek Notlar
- Stream rate'ler (ATTITUDE@20Hz, RANGEFINDER@10Hz) Jetson tarafında `mavlink_interface.py` üzerinden runtime'da `REQUEST_DATA_STREAM` ile set edilir; param'a koymak yerine kod doğrudan komut atar.
- PRECLAND'i etkinleştirmek için Companion (Jetson) tarafında `LANDING_TARGET` MAVLink mesajı 10 Hz akmalı (`docs/PLAN.md` P1.4).
