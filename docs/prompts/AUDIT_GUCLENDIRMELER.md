# AUDIT — Zayıf Noktalar ve Güçlendirmeler

> Bu dokümantasyon, ilk geçişte yazılan 11 modül promptu'nun robotik/güvenli-uçuş bakış açısıyla audit edilmiş halidir. Rapor taahhütleri ve takım kararları **değişmez**; sadece sessiz başarısızlık (silent failure) potansiyeli olan yerler kapatılır.

## Bulgular

| # | Zayıflık | Etki | Düzeltme | Etkilenen Prompt |
|---|---|---|---|---|
| 1 | LoRa üzerinden büyük JPEG (15–25 KB) → 9.6 kbps'te 20–30 sn iletim. Görev başlangıcı kabul edilemez yavaş. | Yarışma süresi yer. Buton → kalkış 30+ sn. | ESP32 tarafında JPEG'i **160×160 grayscale, kalite 65** ile sıkıştır (~3–5 KB). Ayrıca opsiyonel: ESP-NN ile yüz crop + tek face thumbnail gönder. | 01, 02, 04 |
| 2 | AES-CCM **nonce = seq_num**; ESP32 reboot sonrası seq sıfırlanırsa aynı key altında **nonce reuse** → CCM tamamen kırılır. | Konfidensiyalite + integrity tamamen kaybolur. | Seq counter ESP32 NVS'te persistent + her boot'ta +1000 atla. Jetson tarafında "seq_num başlangıç noktası" mesajı (boot beacon). Alternatif: 12-byte random nonce paketle birlikte gönder. | 02 |
| 3 | Multi-chunk reassembly: her chunk CRC'li ama birleştirilmiş payload bütünlüğü ayrıca doğrulanmıyor. İki bağımsız chunk'ın CRC'leri geçerli olabilirken sıra hatası tam JPEG'i bozar. | Sessiz veri bozulması → yanlış yüz embed → yanlış kişiye teslimat. | TRIGGER payload'a `sha256[8]` (ilk 8 byte) ekle. Reassembly sonrası doğrula. | 02, 03 |
| 4 | ESP32, Jetson, Pixhawk farklı saatlerde. Log korelasyonu imkânsız, latency analizi yapılamaz. | Debug imkânsız, post-mortem zayıf. | ESP32: NEO-M8N GPS time'ı RTC'ye yaz. Jetson: chrony + GPSD veya Pixhawk SYSTEM_TIME üzerinden. Tüm loglar `ts_unix_us` field'ı. | 01, 03 |
| 5 | OpenCV ≥4.7'de `cv2.aruco.estimatePoseSingleMarkers` deprecated, kaldırılma yolunda. | Future incompatibility, hata mesajları. | `cv2.solvePnP(objectPoints, corners, K, dist, flags=SOLVEPNP_IPPE_SQUARE)` kullan. Marker köşelerini object frame'de manuel tanımla. | 05 |
| 6 | Custom Visual Servoing PID iyi, ama **ArduCopter PRECLAND + LANDING_TARGET mesajı** zaten production-ready, EKF içine entegre. Custom döngü ile her şeyi sıfırdan tune etmek riskli. | Saha tuning süresi uzar, kararsızlık riski. | İki mod desteği: (a) `PRECLAND` + `MAV_FRAME_BODY_OFFSET_NED LANDING_TARGET` (ArduCopter `PLND_TYPE=1` MAVLink) — production. (b) Custom PID — fallback ve özel manevralar için. Raporun "Visual Servoing PID" taahhüdüne uyar (PRECLAND içi de PID kullanır). | 05, 07 |
| 7 | Lidar Jetson'a bağlı; kamera nadir bakıyor varsayımı + offset yok. Kamera body merkezinde değil → kamera Z ≠ lidar Z. | Yaklaşma 5–10 cm sapma. | `configs/extrinsics.yaml`: `lidar_to_body[xyz]`, `cam_to_body[xyz, rpy]`. Pose hesabında transform uygula. Kalibrasyon scripti (`scripts/calibrate_extrinsics.py`). | 05, 06 |
| 8 | Geofence yok. Yarışma sahası dışına çıkış / kazara uzaklaşma için hiçbir koruma yok. | Hardware kaybı, jüri ceza. | ArduCopter `FENCE_ENABLE=1, FENCE_TYPE=7, FENCE_RADIUS=200, FENCE_ALT_MAX=50, FENCE_ACTION=1 (RTL)`. Polygon fence yarışma alanı koordinatlarıyla yüklenmeli. | 07, 08 |
| 9 | `SET_POSITION_TARGET_LOCAL_NED` yaw alanı belirsiz. `YAW_RATE_IGNORE` set ama `YAW_IGNORE` set değil → yaw=0 absolute (radyan) komut olarak yorumlanabilir → kuzeye dönmeye çalışır. | Yaw oscillation veya yön kaybı. | Type mask'a `POSITION_TARGET_TYPEMASK_YAW_IGNORE` da ekle. Veya yaw'ı drone'un current heading'ine sabitle. | 05, 07 |
| 10 | State machine transition'da eski faza ait async task'lar (servoing loop, face verify loop) iptal edilmiyor → arka planda yanlış komut gönderebilirler. | Race condition, kontrol komutu çakışması. | Her phase için `asyncio.TaskGroup` veya cancel scope. Transition öncesi `current_phase_tasks.cancel()` + `await gather(..., return_exceptions=True)`. | 08 |
| 11 | DELIVERING/LANDING sırasında devrilme/çarpışma tespiti yok. IMU verisi monitor edilmiyor. | Devrilse bile servo açılır, motor dönmeye devam edebilir. | Jetson'da MAVLink `RAW_IMU` veya `ATTITUDE` dinle: |roll|>45° veya |pitch|>45° veya |az|>3g → EMERGENCY_KILL (DISARM + MOTOR_INTERLOCK). | 08, 09 |
| 12 | Bağımlılık versiyonları açık (`>=`). JetPack/CUDA/TRT/OpenCV güncellemesinde TRT engine, pymavlink dialect uyumsuzlukları silent break üretir. | Yarışma günü deploy patlar. | `uv lock` / `poetry.lock` zorunlu. TRT engine cache key: `{model}_{trt_version}_{jetpack_version}_{precision}.engine`. ESP32 tarafında `platformio.ini` lib pin (`@^x.y.z`). | 03, 04 |

## Ek Sertleşmeler (önceden listelenmemiş ama önemli)

13. **Sensor pre-arm check**: Jetson, ARM komutu göndermeden önce: GPS fix≥10 sat, lidar healthy, kamera frame received, MAVLink heartbeat OK, face_ref_ready. Aksi durumda IDLE'da kal, UI'da neden göster.
14. **RC override failsafe**: Pilot her zaman radyo kumandası ile manual mode'a alıp toparlayabilmeli. `RC_OVERRIDE` Jetson tarafından engellenmemeli. Pilot priority **mutlak**.
15. **Battery voltage tabanlı failsafe**: SOC% yük altında yanıltıcı. Pixhawk `BATT_LOW_VOLT=22.0V (6S)`, `BATT_CRT_VOLT=21.0V`, `BATT_FS_LOW_ACT=2 (RTL)`, `BATT_FS_CRT_ACT=1 (LAND)`.
16. **Log download otomasyonu**: Görev sonrası Jetson, MAVLink `LOG_REQUEST_LIST` ile Pixhawk dataflash log'unu çeker, JSONL ile birleştirir, `runs/YYYYMMDD_HHMM/` altına atar.
17. **Watchdog**: `systemd` `Restart=on-failure` + Pixhawk'tan Jetson sağlığı (heartbeat) kesilirse failsafe.
18. **Reboot recovery kuralı**: Jetson mid-mission reboot → state IDLE, fakat MAVLink'ten mevcut mode'u oku; eğer AUTO/GUIDED/RTL aktifse Jetson kendini sadece monitor moda alır, yeni komut göndermez (Pixhawk başına buyruk RTL'i bitirir).
19. **LoRa link kalitesi telemetri**: RSSI, SNR, packet loss rate ESP32 `MSG_TELEMETRY`'ye eklenmeli.
20. **Yaw alignment for face cam**: Marker'a kilitlenmek yeterli değil; alıcının kameraya bakacak şekilde drone'un yaw'ını ped yönüne çevirmesi lazım. APPROACHING sonunda yaw → ped üzerindeki yön işaretine (marker rotation'dan) hizala.

## Etki Skoru

| Bulgu | Sessiz başarısızlık potansiyeli | Yarışma kayıp riski | Düzeltme maliyeti |
|---|---|---|---|
| 1 (LoRa JPEG) | YOK (yavaş ama görünür) | Yüksek (zaman) | Düşük |
| 2 (nonce reuse) | KRİTİK | Orta | Düşük |
| 3 (payload hash) | YÜKSEK | Yüksek (yanlış kişi!) | Düşük |
| 4 (time sync) | DEBUG | Düşük | Orta |
| 5 (solvePnP) | DÜŞÜK (deprecation) | Düşük | Düşük |
| 6 (PRECLAND) | ORTA | Yüksek (iniş güvenliği) | Orta |
| 7 (extrinsics) | YÜKSEK (sessiz sapma) | Orta | Orta |
| 8 (geofence) | YOK | Yüksek | Düşük |
| 9 (yaw mask) | YÜKSEK | Orta | Düşük |
| 10 (task cancel) | YÜKSEK | Yüksek | Orta |
| 11 (crash det.) | KRİTİK | Yüksek | Düşük |
| 12 (version pin) | YÜKSEK | Yüksek (deploy) | Düşük |

## Uygulama Listesi

- [ ] Modül 02 → seq persistent + payload SHA-256 + opsiyonel embedding-only mod
- [ ] Modül 01 → JPEG 160×160 grayscale Q65 + GPS time RTC sync
- [ ] Modül 03 → pre-arm checker + time sync + log download + reboot recovery
- [ ] Modül 04 → embedding-only path + TRT engine versioned cache
- [ ] Modül 05 → solvePnP + extrinsics transform + yaw_ignore mask
- [ ] Modül 06 → extrinsics yaml + lidar mount offset
- [ ] Modül 07 → PRECLAND mod + geofence + battery voltage failsafe + RC priority
- [ ] Modül 08 → TaskGroup ile phase cancellation + failsafe priority queue + crash detection
- [ ] Modül 09 → IMU monitor abort + servo ack zorunluluk
- [ ] Tüm modüller → version lock dosyaları
- [ ] **YENİ**: `MASTER_SYSTEM_PROMPT.md` — single-shot full system builder
