# QUESTIONS_FOR_TEAM.md — Takım Kararları

> Takım kararı: **resmi yarışma raporuna sadık kalınacak**. Her soru için
> rapor uyumlu recommended seçenek alındı ve kod tarafına uygulandı. Bu
> dosya kararların gerekçesini ve mevcut durumu listeler.

---

## Karar Verilmiş — Recommended (rapor uyumlu)

### Q1 — Yüz Görüntüsü Transferi → **(a) JPEG transfer**
**Gerekçe:** Rapor 3.3.1.1 açıkça "FACE IMAGE CAPTURE → packet → drone" diyor. `recipient_id`-only yaklaşımı bu taahhüde uymaz.

**Uygulama (Sprint 2 P1.2 — TAMAM):**
- `firmware/esp32_ground_station/ground_station.ino` `sendFaceDelivery()` → kameradan JPEG yakalar (160×120 QQVGA, kalite 25 ≈ Q65), `FACE_IMAGE_BEGIN` + N × `FACE_IMAGE_CHUNK` paketler.
- `onboard/lora_receiver.py` `ImageReassembler` ile birleştirir, `FaceDelivery(gps, jpeg)` üretir.
- `onboard/mission.py` `_do_wait_packet` → `verifier.enroll_from_jpeg()` ile referans yüzü tek atımda enroll eder.
- Legacy `DELIVERY_REQUEST` (recipient_id) hâlâ destekli — operatör tercih ederse fallback.

---

### Q2 — LoRa Güvenliği → **(a) AES-128-CCM + persistent seq + SHA-256**
**Gerekçe:** Rapor 1.2.2 "şifrelenmiş veri iletimi" + 3.4.3 "veri paketi şifreleme algoritmaları takım üyelerimiz tarafından yazılmıştır" — şifreleme rapor taahhüdü.

**Uygulama (Sprint 2 P1.1 — TAMAM):**
- `onboard/packet_protocol.py` ve `firmware/.../packet_protocol.h`:
  - 32-bit monotonik seq (8-bit wrap fixi).
  - AES-128-CCM (Python `cryptography.AESCCM`, ESP32 `mbedtls/ccm.h`). Nonce = seq32 + msg_type + chunk + "KOKPIT0" pad → 13 byte.
  - SHA-256 ilk 8 byte payload hash header'da.
  - Replay protection: LRU son 256 seq Jetson tarafında.
  - Boot beacon (`MSG_BOOT_BEACON`) — ESP32 reboot sonrası seq pencere resync.
- ESP32 NVS `Preferences` "kokpit/seq" — boot'ta +1000 sıçra, nonce reuse imkânsız.
- Anahtar: `~/.config/kokpit/lora.key` (Jetson) + ESP32 NVS "kokpit/aes_key" (16 byte). `KOKPIT_AES_ENABLED` define ile aktif. Anahtar yoksa plaintext fallback (geliştirme kolaylığı).

---

### Q3 — Yarışma Alanı GPS Köşeleri → **TAKIMA SORULMALI**
Saha henüz duyurulmadıysa boş bırak. Duyurulunca `ardupilot/kokpit_arena.poly` üret + `mavlink_interface.setup_geofence(polygon, alt_max=50)` çağrılır.

Default geofence aktif: 200 m yarıçap, 50 m max yükseklik, RTL on breach.

---

### Q4 — Donanım Mevcudiyeti → **TAKIMA SORULMALI**
Listenin doldurulması saha test planını belirler. Tüm donanım yoksa SITL + sahte LoRa ile gelişim devam eder.

---

### Q5 — Async Refactor → **(b) Minimal threading.Event cancel**
**Gerekçe:** Mevcut `threading` tasarımı çalışıyor; full asyncio rewrite riski yarışma takvimine yakın. Phase cancellation ihtiyacı `threading.Event` ile yeterli düzeyde çözülür.

**Uygulama (Sprint 3 P2.2 — TAMAM):**
- `onboard/mission.py` `self._cancel_event = threading.Event()` eklendi.
- `request_abort()` event set eder, blocking loop'lar polling yerine event.is_set() bakar.
- Failsafe priority queue (P0.2 — TAMAM) farklı failsafe'lerin önceliklendirilmesini sağlar.

---

### Q6 — Yüz Tanıma Backend → **(c) TensorRT default + dlib fallback**
**Gerekçe:** Rapor 2.1.2 ve 3.3.1.2'de **"TensorRT destekli Evrişimli Sinir Ağları"** açıkça yazılı. TRT primary olmalı; dlib (mevcut `face_recognition`) Jetson hardware hazır olmadan geliştirme için fallback.

**Uygulama (Sprint 2 P1.3 — TAMAM):**
- `onboard/face_verifier.py` `TRTBackend` (RetinaFace MnetV0.25 + ArcFace R50, 5-point align, cosine similarity, ArcFace 112x112).
- `tools/build_face_trt.py` ONNX → TensorRT engine builder, cache key `{model}_{trt}_{jetpack}_{precision}.engine` (Jetson dışı graceful skip).
- `KOKPIT_TRT_DIR` env override; engine yok/import yok → dlib `face_recognition` fallback + uyarı log'u.
- `FaceVerifier(force_backend="trt")` API.
- Test (`tests/test_face_trt.py`): engine lookup, missing-engine fallback, Jetson smoke.
- Donanım TODO: gerçek `.engine` dosyaları Jetson Orin Nano üzerinde JetPack 6.x ile build edilmeli.

---

### Q7 — PRECLAND vs Custom PID → **(c) Hibrit: PID primary + PRECLAND complement**
**Gerekçe:** Rapor 3.3.1.3'te "Visual Servoing PID Loop algoritması" açıkça yazılı — PID primary olmalı. ArduCopter PRECLAND yerleşik Kalman'ı yan tarafta çalışıp ek dayanıklılık sağlayabilir (rapor PRECLAND'i yasaklamıyor).

**Uygulama (Sprint 2 P1.4 — TAMAM):**
- `onboard/visual_servo.py` her tespit sonrası `mavlink.send_landing_target(angle_x, angle_y, distance)` çağırır.
- `ardupilot/kokpit_precland.param`: `PLND_ENABLED=1, PLND_TYPE=1` (MAVLink), `PLND_EST_TYPE=1` (Kalman).
- Custom PID hız döngüsü görsel servoing'i sürdürür; PRECLAND Pixhawk EKF içinde paralel pozisyon kestirimine katkı yapar.

---

### Q8 — ArduCopter Param Dosyası Sahipliği → **(a) Repo'da maintain**
**Uygulama (Sprint 1 P0.5 — TAMAM):**
- `ardupilot/kokpit_baseline.param`
- `ardupilot/kokpit_companion.param` (TELEM2 921600)
- `ardupilot/kokpit_precland.param`
- `ardupilot/kokpit_lidar.param` (TFS20)
- `ardupilot/kokpit_servo.param` (AUX1/SERVO9)
- `ardupilot/kokpit_failsafe.param` (batarya voltaj, RC, GCS, EKF, crash)
- `ardupilot/kokpit_geofence.param`

MissionPlanner: Full Parameter List → Load from file. Sırayla yükle, her birinden sonra "Compare Params" + kontrol et.

---

### Q9 — LoRa Frekansı → **433 MHz (TR ISM bandı)**
Rapor 3.2.4 ve donanım listesi 433T20D kullandığımızı belirtiyor. Türkiye 433.05–434.79 MHz ISM bandı (BTK onaylı). LoRa modülü bu band içinde kalmalı.

---

### Q10 — Yüz Dataset Enrollment → **Demo öncesi alıcı yüzü ESP32 ile yakalanır**
Yeni mod sayesinde önceden enroll gerekmez — buton anında alıcı yüzü ESP32 kamerasından yakalanıp drone'a gönderilir. Drone tek atımda referans embedding üretir.

---

### Q11 — Saha Test Takvimi → **TAKIMA SORULMALI**
Sprint 4 zorunlu (2 gün): kalibrasyon + PID tuning + ArduCopter AUTOTUNE + failsafe test + 3 rehearsal uçuş.

---

### Q12 — Yedek Donanım → **TAKIMA SORULMALI**
Yarışma günü için minimum: 2× LiPo, 4× pervane, 1× ESP32, 1× motor.

---

## Sprint 0 Bug Atama (TAMAM)

| Bug | Dosya | Durum |
|---|---|---|
| `EKF_ATTITUDE` AttributeError | `onboard/mavlink_interface.py` | TAMAM (literal bit flags kullanıldı) |
| Yaw mask `YAW_IGNORE` bit eksik | `onboard/mavlink_interface.py` | TAMAM (`IGNORE_YAW | IGNORE_YAW_RATE`) |
| `mission_start` None kontrol | `onboard/mission.py` | TAMAM (None-safe + transition guard) |
| 8-bit seq → 32-bit + NVS persistent | `firmware/.../ground_station.ino` | TAMAM (Preferences NVS + boot +1000 jump) |
| Servo ACK + retry | `onboard/mavlink_interface.py` `set_servo()` | TAMAM (3 retry + COMMAND_ACK timeout 500 ms) |
| `SimLoRaReceiver.wait_for_delivery` event | `onboard/lora_receiver.py` | NO-OP (`queue.get(timeout)` zaten event-based) |

---

## Bekleyen — Donanım Hazır Olunca

1. TensorRT ArcFace engine build (Jetson + JetPack 6.x gerekir)
2. Kamera kalibrasyon (chessboard 20 pose)
3. Lidar/kamera extrinsics ölçümü → `onboard/configs/extrinsics.yaml`
4. PID gain tuning (saha, 10–20 iterasyon)
5. ArduCopter AUTOTUNE
6. Geofence GPS köşelerinin sahada ölçülmesi
7. Saha test uçuşları (Sprint 4)

---

**Toplantı tarihi:** _____ **Onaylayan:** _____ (rapor sorumlusu)
