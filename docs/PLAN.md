# PLAN.md — Kokpit UAV Roadmap

> **Amaç:** Mevcut repo state'ini Teknofest 2026 yarışma seviyesine taşımak. Bu plan, `docs/prompts/AUDIT_GUCLENDIRMELER.md` denetiminden çıkan tüm açıkları kapatır.
>
> **Karar Modeli:** Her görev `P0` (uçuş güvenliği — yapılmadan uçma) / `P1` (rapor taahhüdü — yapılmadan yarışma puanı kaybı) / `P2` (kalite/operasyon — yapılmadan demo başarısız riski yüksek) ile etiketli.

---

## 🔴 SPRINT 0 — Kritik Bug Fix (1 gün)

| # | Görev | Dosya:Satır | Sorumlu | Tahmini |
|---|---|---|---|---|
| 0.1 | `EKF_ATTITUDE` AttributeError düzelt | `onboard/mavlink_interface.py:153` | Zeki | 30 dk |
| 0.2 | Yaw mask `YAW_IGNORE` bitini set et | `onboard/mavlink_interface.py:262,281` | Zeki | 30 dk |
| 0.3 | `mission.run()` `mission_start` `None` kontrolü | `onboard/mission.py:131-178` | Arda | 30 dk |
| 0.4 | 8-bit `seqCounter` → 32-bit + NVS persistent | `firmware/esp32_ground_station/ground_station.ino:65` + `packet_protocol.h` | Attia | 2 sa |
| 0.5 | `MAV_CMD_DO_SET_SERVO` ACK bekleme + retry | `onboard/mavlink_interface.py` (yeni `set_servo_acked`) | Zeki | 1 sa |
| 0.6 | `lora_receiver.SimLoRaReceiver.wait_for_delivery` mutex/event | `onboard/lora_receiver.py` | Arda | 30 dk |

**Çıkış kriteri:** `make test` yeşil, `make demo` AttributeError olmadan tam akış geçer.

---

## 🔴 SPRINT 1 — Uçuş Güvenliği (3 gün, P0)

### P0.1 — Crash Detection
- `onboard/mavlink_interface.py`: `ATTITUDE` stream'i 20 Hz'e çek (`MESSAGE_INTERVAL`)
- `onboard/mission.py`: yeni `_crash_monitor()` thread; |roll|>45° veya |pitch|>45° veya |az|>3g (RAW_IMU)
- Tetiklendi mi → `EMERGENCY_DISARM` (`MAV_CMD_COMPONENT_ARM_DISARM` param2=21196 force magic) + servo PWM 1000 kilitle + state.phase = ABORTED
- Test: SITL'de `SIM_GYR_RND` ile devirme, disarm doğrulanır
- **Sorumlu:** Arda + Zeki | **Tahmini:** 1 gün

### P0.2 — Failsafe Priority Queue
- `onboard/mission.py`: `_abort` bool yerine `_failsafe_heap` (heapq, priority)
- Priorite: `USER_ABORT(100) > CRASH(95) > BATTERY_CRT(90) > LINK_LOST(80) > BATTERY_LOW(70) > GPS_LOST(60) > MARKER_LOST(50) > FACE_TIMEOUT(40) > GEOFENCE(30)`
- Her tick'te en yüksek priority kazanır, eylem `RTL` / `LAND_HERE` / `ABORT` matrisinden
- Test: aynı tick'te 2 failsafe → doğru kazanır
- **Sorumlu:** Arda | **Tahmini:** 4 sa

### P0.3 — Servo Safety Guards
- `onboard/package_dropper.py` `drop()` içine 6-katman:
  1. `state.phase == DROP_PACKAGE`
  2. `state.face_verified == True`
  3. `state.marker_locked == True`
  4. `1.0 <= lidar_alt <= 2.5`
  5. MAVLink `set_servo` ACK alındı
  6. `|roll|<15° and |pitch|<15°` snapshot
- Boot'ta `set_servo(9, 1000)` 2 kez (idempotent boot lock)
- Test: her guard'ı tek tek false yap → `drop()` False döner, servo komutu gönderilmez
- **Sorumlu:** Arda | **Tahmini:** 4 sa

### P0.4 — ArduCopter Geofence Upload
- `onboard/mavlink_interface.py`: `setup_geofence(polygon_points, alt_max)` metodu, `MISSION_ITEM_INT` ile polygon yükle + `FENCE_ENABLE=1` param set
- Boot'ta `ardupilot/kokpit_arena.poly` oku, otomatik yükle
- Test: SITL'de drone fence dışına manuel git → ArduCopter RTL tetikler
- **Sorumlu:** Zeki | **Tahmini:** 4 sa

### P0.5 — RC Pilot Priority + ArduCopter Failsafe Param
- `ardupilot/kokpit_failsafe.param` yaz (BATT_LOW_VOLT, FS_THR_ENABLE, FS_GCS_ENABLE, RC_OVERRIDE_TIME=0)
- Jetson **asla** `RC_OVERRIDE` göndermez (kontrol et: yok)
- `mission.py`: pilot Manual/Stabilize'a alırsa `state.phase = PILOT_OVERRIDE`, Jetson read-only
- **Sorumlu:** Zeki | **Tahmini:** 3 sa

### P0.6 — Lidar RANGEFINDER MAVLink Subscribe
- `onboard/mavlink_interface.py`: `RANGEFINDER` mesajını dinle, `state.lidar_alt` yaz
- `MESSAGE_INTERVAL` ile 10 Hz iste
- `ardupilot/kokpit_lidar.param`: TFS20 paramları (`RNGFND1_TYPE=10`, `RNGFND1_ORIENT=25`, `EK3_RNG_USE_HGT=70`)
- Test: SITL `SIM_SONAR_SCALE=12.12` ile rangefinder enjekte, mesaj ulaşıyor mu
- **Sorumlu:** Arda + Attia (donanım kablo) | **Tahmini:** 4 sa

---

## 🟡 SPRINT 2 — Rapor Taahhüdü (4 gün, P1)

### P1.1 — LoRa Şifreleme + Bütünlük (KRİTİK GÜVENLİK)
- `firmware/esp32_ground_station/packet_protocol.h` + `onboard/packet_protocol.py`:
  - AES-128-CCM (mbedTLS / `cryptography.AESCCM`)
  - 4-byte monotonik seq (NVS persistent, boot'ta +1000 sıçra)
  - 8-byte SHA-256 payload hash (chunk reassembly sonrası)
  - Replay protection (LRU 256 seq)
- Anahtar: `secrets/lora.key` (.gitignore), `secrets/lora.key.example` commit'li
- Test: roundtrip C↔Python, replay reject, bit-flip → decrypt fail
- **Sorumlu:** Attia + Arda | **Tahmini:** 2 gün

### P1.2 — Yüz Görüntüsü LoRa İletimi (rapor taahhüdü)
- Mevcut `recipient_id` yaklaşımı rapora aykırı; rapor "Face Image Capture → packet → drone" diyor
- ESP32: kameradan yakala → 160×160 grayscale → JPEG Q65 (~3–5 KB) → chunk'lı LoRa (paket başı 58 byte payload)
- Jetson: chunk reassembly → SHA verify → embed → `state.ref_embedding`
- **Geri uyumlu mod**: `recipient_id` da desteklenmeye devam etsin (config flag)
- **Sorumlu:** Attia + Arda | **Tahmini:** 1 gün

### P1.3 — TensorRT Yüz Tanıma (opsiyonel ama tavsiye)
- Mevcut dlib `face_recognition` Jetson'da CPU only → hover'da 1–2 FPS, marjinal
- ArcFace R50 ONNX → TensorRT FP16 (10+ FPS) — `onboard/face_verifier.py` opsiyonel backend
- Engine cache: `{model}_{trt_version}_{jetpack}_{precision}.engine`
- dlib fallback olarak kalır
- **Sorumlu:** Arda | **Tahmini:** 1 gün

### P1.4 — PRECLAND + LANDING_TARGET
- `onboard/visual_servo.py`: yeni `precland_mode()` — ArUco poz → `LANDING_TARGET` MAVLink mesajı 10 Hz
- `ardupilot/kokpit_precland.param`: `PLND_ENABLED=1, PLND_TYPE=1, PLND_EST_TYPE=1`
- ArduCopter `LAND` modunda otomatik centering
- Custom PID `body_velocity_mode()` fallback olarak korunur
- Test: SITL `LANDING_TARGET` inject, drone marker üzerine iner
- **Sorumlu:** Arda | **Tahmini:** 6 sa

### P1.5 — Yaw Alignment (delivery aşamasında)
- APPROACHING sonunda ArUco rotation'dan ped yön referansı al
- `mavlink.condition_yaw(target_heading)` ile drone yaw → ped yönüne
- Alıcı drone'a değil, drone alıcıya bakar
- **Sorumlu:** Arda | **Tahmini:** 3 sa

### P1.6 — Stream Rate'leri Doğru Set Et
- `onboard/mavlink_interface.py:101-103` tek `MAV_DATA_STREAM_ALL@5Hz` yetersiz
- `MESSAGE_INTERVAL` ile per-mesaj: ATTITUDE@20, GLOBAL_POSITION_INT@5, RANGEFINDER@10, BATTERY_STATUS@1, RAW_IMU@20, HOME_POSITION@0.5, SYSTEM_TIME@0.2
- **Sorumlu:** Zeki | **Tahmini:** 1 sa

---

## 🟢 SPRINT 3 — Operasyon Kalitesi (3 gün, P2)

### P2.1 — Time Sync
- ESP32: NMEA `$GNRMC` UTC → RTC (`settimeofday`)
- Jetson: MAVLink `SYSTEM_TIME` → `os.settimeofday` veya chrony
- Tüm loglar `ts_unix_us` field'ı
- **Sorumlu:** Zeki + Attia | **Tahmini:** 4 sa

### P2.2 — Async/TaskGroup Refactor (opsiyonel)
- `mission.py` blocking thread design'ı `asyncio.TaskGroup` ile değiştir
- Phase transition'da tüm önceki phase task'larını cancel
- **Karar gerekli (sorulara bak)**: takım kabul ederse büyük refactor (1 gün), etmezse minimal `threading.Event` ile cancel
- **Sorumlu:** Arda | **Tahmini:** 1 gün (full) / 3 sa (minimal)

### P2.3 — Gazebo SITL + 6 Senaryo
- `simulation/gazebo/`: ArduCopter SITL + Gazebo Garden + ped/marker world
- 6 senaryo: happy, marker_lost, face_mismatch, link_lost, battery_low, gps_lost
- CI'a entegre (zaten `.github/workflows/ci.yml` skeleton var)
- **Sorumlu:** Arda | **Tahmini:** 1 gün

### P2.4 — Log Download Otomasyonu
- Görev sonu Jetson Pixhawk dataflash log `LOG_REQUEST_LIST` + `LOG_REQUEST_DATA`
- `runs/YYYYMMDD_HHMMSS/dataflash.bin` + `jetson.jsonl` + `merged.csv`
- **Sorumlu:** Zeki | **Tahmini:** 4 sa

### P2.5 — Watchdog + systemd
- `systemd/kokpit-mc.service` (Restart=on-failure, WatchdogSec=15)
- `main.py` 5 sn'de bir `sd_notify("WATCHDOG=1")`
- **Sorumlu:** Zeki | **Tahmini:** 2 sa

### P2.6 — Extrinsics + Kalibrasyon
- `onboard/configs/extrinsics.yaml`: `cam_to_body`, `lidar_to_body` (x,y,z,rpy)
- `tools/calibrate_extrinsics.py` interaktif rehber
- `visual_servo.py` ve `sensor_fusion` pose hesabında transform uygula
- **Sorumlu:** Arda | **Tahmini:** 4 sa

### P2.7 — LoRa Link Telemetri (RSSI/SNR)
- ESP32 E32 register'larından RSSI oku → TELEMETRY paketinde
- Jetson: dashboard'a yansıt
- **Sorumlu:** Attia | **Tahmini:** 2 sa

### P2.8 — Reboot Recovery
- Jetson boot: MAVLink mode oku; AUTO/GUIDED/RTL aktif ise `MissionPhase.READ_ONLY`
- **Sorumlu:** Arda | **Tahmini:** 2 sa

---

## 🔵 SPRINT 4 — Saha Hazırlığı (2 gün)

### S4.1 — Kalibrasyon Turu
- Kamera kalibrasyon (chessboard 20 pose) → `camera_calibration.npz`
- Kamera-lidar mount offset ölç → `extrinsics.yaml`
- ESC + motor + radyo kalibrasyon
- Kompas (dönerek)
- Yüz dataset enroll: alıcı kişi 5 farklı açı/ışıkta → `data/faces/`

### S4.2 — PID Tuning (saha)
- SITL'de kaba gain'ler bul
- Gerçek hover'da tepki test → 10-20 iterasyon
- Wind/payload offset

### S4.3 — ArduCopter Saha Tuning
- `AUTOTUNE` modu (her eksen 5–10 dk)
- Geofence GPS köşelerini sahada ölç, `kokpit_arena.poly` güncelle

### S4.4 — Test Uçuşları
- Manual → Stabilize → AltHold → Loiter → Guided kademe
- Failsafe testleri (RC kapat, batarya yalandan düşür, GPS kapat)
- Full mission rehearsal × 3

### S4.5 — Yarışma Günü Checklist
- `docs/KILAVUZ.md` kontrol kartı bölümünü kullan

---

## Özet Effort Tahmini

| Sprint | Effort | Çıkış |
|---|---|---|
| 0 — Bug fix | 1 gün | `make test` yeşil |
| 1 — Uçuş güvenliği | 3 gün | SITL'de failsafe testleri yeşil |
| 2 — Rapor taahhüdü | 4 gün | LoRa şifreli + yüz JPEG + PRECLAND |
| 3 — Operasyon | 3 gün | Gazebo CI + log + watchdog |
| 4 — Saha | 2 gün | Donanım kalibre + test uçuşları |
| **TOPLAM** | **13 gün** | Demo-ready |

**Yarışma günü öncesi en az 3 gün rezerv olmalı** (toplam ~16 gün minimum takvim).

## İzleme

Tamamlanan görevler bu dosyada checkbox'lanır:
- [ ] Sprint 0
- [ ] Sprint 1
- [ ] Sprint 2
- [ ] Sprint 3
- [ ] Sprint 4

Bloker / risk → `docs/QUESTIONS_FOR_TEAM.md`'ye yaz, takım toplantısında çöz.
