# QUESTIONS_FOR_TEAM.md — Karar Bekleyen Sorular

> Bu sorular `docs/PLAN.md` sprint'lerini başlatmadan önce takımca cevaplanmalı. Cevaplar bu dosyaya işlenecek, sonra plan kesinleşecek.

---

## 🔴 BLOCKING — Cevap Olmadan İlerlenemez

### Q1 — Yüz Görüntüsü Transferi (rapor uyumu)
**Soru:** Yarışma raporumuz "Face Image Capture → packet → drone" diyor. Mevcut kod sadece `recipient_id` gönderiyor, gerçek görüntü değil.
- (a) ✅ Rapora uyalım: LoRa'dan 160×160 grayscale Q65 JPEG (~4 KB) chunk'lı gönder (5 sn iletim)
- (b) ⚠️ `recipient_id` ile devam et + raporu güncelle/jüriye açıkla
- (c) ✅ Hibrit: ikisi de desteklensin, config flag ile seç

**Cevap:**

---

### Q2 — LoRa Güvenlik Kapsamı
**Soru:** LoRa şu an plaintext + CRC + 8-bit seq. 433 MHz menzilindeki herkes sahte tetik gönderebilir / replay yapabilir.
- (a) ✅ AES-128-CCM + 32-bit persistent seq + SHA-256 payload hash (önerilen — 2 gün)
- (b) ⚠️ Sadece HMAC-SHA256 + seq (integrity ama gizlilik yok — 1 gün)
- (c) ❌ Mevcut korumayı koru (yarışma kapsamı için kabul edilebilir bul)

**Cevap:**

---

### Q3 — Yarışma Alanı GPS Köşeleri
**Soru:** Geofence için yarışma sahasının 4–6 köşesinin GPS koordinatları gerekiyor.
- Saha henüz duyurulmadı mı? (Beklenecek)
- Duyuruldu mu? (Koordinatları paylaş, `ardupilot/kokpit_arena.poly` üretilecek)

**Cevap (lat, lon × 4-6):**

---

### Q4 — Donanım Mevcudiyeti
Hangi donanımlar **şu an** test için elde? (Sahaya çıkmadan ne kadar HIL yapabiliriz?)

| Donanım | Var (Y/N) | Notlar |
|---|---|---|
| Pixhawk 2.4.8 | | |
| Jetson Orin Nano | | |
| IMX219 kamera | | |
| Benewake TFS20 lidar | | |
| Holybro M9N GPS | | |
| ESP32 TTGO T-Display | | |
| NEO-M8N GPS (yer) | | |
| OV5640 (yer kamera) | | |
| LoRa E32 433T20D ×2 | | |
| SIK Telemetry V3 | | |
| Drone frame ZD550 + motor + ESC + LiPo | | |
| Servo + paket bırakma mekanizması | | |

---

## 🟡 ARCHITECTURE — Takım Onayı

### Q5 — Async Refactor Kapsamı
**Soru:** `mission.py` şu an blocking + threading. Phase transition'da eski phase task'ları cancel edilmiyor → race condition riski (servoing failsafe sırasında hala komut atabilir).
- (a) ✅ `asyncio.TaskGroup` ile full refactor (1 gün, daha temiz, modern)
- (b) ⚠️ Minimal: `threading.Event` cancel flag'leri serpiştir (3 sa, mevcut yapıyı koru)
- (c) ❌ Mevcut tasarımı koru, race condition'ı kabul et

**Cevap:**

---

### Q6 — Yüz Tanıma Backend
**Soru:** Şu an dlib `face_recognition` (CPU only) — Jetson'da 1–2 FPS, doğrulama uzun sürer.
- (a) ✅ TensorRT InsightFace ArcFace R50 (FP16, 10+ FPS, kurulumu zahmetli)
- (b) ⚠️ Mevcut dlib (kabul edilebilir, hover süresini uzat)
- (c) ✅ İkisi de — dlib fallback, TRT default

**Cevap:**

---

### Q7 — PRECLAND vs Custom PID
**Soru:** ArduCopter yerleşik PRECLAND (`LANDING_TARGET` mesajı) hazır, test edilmiş. Custom PID'imiz tuning gerektirir.
- (a) ✅ PRECLAND primary, custom PID fallback
- (b) ⚠️ Custom PID primary (kontrol bizde, raporda "Visual Servoing PID" diyoruz)
- (c) ✅ İkisi de implemente, config flag ile seç (önerilen)

**Cevap:**

---

### Q8 — ArduCopter Param Dosyası Sahipliği
**Soru:** `ardupilot/*.param` dosyalarını kim üretip commit edecek?
- (a) Repo'da maintain (versionlu, herkes pull edip MissionPlanner'dan yükler) ✅
- (b) MissionPlanner'da manuel, paylaşmadan
- (c) Hibrit (baseline repo'da, saha tuning manuel)

**Cevap (kim) / (hangi):**

---

## 🟢 OPERASYONEL — Hızlı Cevap

### Q9 — LoRa Frekansı Yasal Onay
**Soru:** Türkiye'de 433 MHz LoRa kullanımı yasal mı? Yarışma izin verilen frekansları belirtti mi?
- Yarışma şartnamesi: ?
- Yasal band: 433.05–434.79 MHz ISM (Türkiye için onaylı kanal)

**Cevap:**

---

### Q10 — Yüz Veri Seti Enrollment
**Soru:** Alıcı kişinin yüzü ne zaman enroll edilecek?
- (a) Yarışma günü, sahada, jüri/yetkili kişi ile
- (b) Önceden çoklu kişi (jüri kim olursa)
- (c) Demo öncesi tek kişi belirlenip enroll

**Cevap:**

---

### Q11 — Saha Test Takvimi
**Soru:** Demo öncesi ne kadar saha testi yapılabilecek?
- Kaç gün?
- Hangi sahada (üniversite kampüsü / yarışma alanı / başka)?
- Pilot kim?

**Cevap:**

---

### Q12 — Yedek Donanım
**Soru:** Yarışma günü kritik donanım kırılırsa yedek var mı?
- Yedek pervane: var/yok
- Yedek motor: var/yok
- Yedek ESP32: var/yok
- Yedek LiPo: var/yok
- Yedek RPi/Jetson: var/yok

**Cevap:**

---

## 🔧 BUG ATAMA (Sprint 0 hızlı)

| Bug | Kim Düzeltecek |
|---|---|
| `EKF_ATTITUDE` AttributeError (`mavlink_interface.py:153`) | |
| Yaw mask `YAW_IGNORE` bit eksik (`mavlink_interface.py:262,281`) | |
| `mission.run()` `mission_start` None kontrol (`mission.py:131-178`) | |
| 8-bit seq → 32-bit + NVS persistent (`ground_station.ino:65`) | |
| Servo ACK + retry | |
| `SimLoRaReceiver.wait_for_delivery` event yerine sleep | |

---

## 📅 Sonraki Adımlar

1. Bu dosyayı takım toplantısında doldur (1 saat)
2. Cevaplara göre `docs/PLAN.md` Sprint 1–4 görev atamalarını sabitle
3. Sprint 0 (1 gün) bug fix → CI yeşil
4. Sprint 1 başla

**Toplantı tarihi:** _____
**Katılımcılar:** Arda, Zeki, Attia, Enes (takım sorumlusu)
**Karar verme yöntemi:** Çoğunluk + Enes veto hakkı (raporlama sorumlusu olarak)
