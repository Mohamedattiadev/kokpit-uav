# KOKPIT İHA — Detaylı Kullanım Kılavuzu

Bu kılavuz, yazılımı sıfırdan kurup test etmekten yarışma günü saha
operasyonuna kadar **adım adım** her şeyi anlatır. Sıralı oku; atlama.

İçindekiler:
1. [Sistem genel bakış](#1-sistem-genel-bakış)
2. [Gereken donanım ve yazılım](#2-gereken-donanım-ve-yazılım)
3. [Kurulum](#3-kurulum)
4. [Kablolama](#4-kablolama)
5. [ArduPilot / Pixhawk parametreleri](#5-ardupilot--pixhawk-parametreleri)
6. [Kalibrasyon](#6-kalibrasyon)
7. [Yüz veri seti hazırlama](#7-yüz-veri-seti-hazırlama)
8. [Test (3 katman)](#8-test-3-katman)
9. [Saha operasyon prosedürü](#9-saha-operasyon-prosedürü)
10. [Parametre referansı (config.py)](#10-parametre-referansı-configpy)
11. [Görev akışı — durum durum](#11-görev-akışı--durum-durum)
12. [Sorun giderme](#12-sorun-giderme)
13. [Acil durum ve güvenlik](#13-acil-durum-ve-güvenlik)
14. [Yarışma günü hızlı kontrol kartı](#14-yarışma-günü-hızlı-kontrol-kartı)

---

## 1. Sistem genel bakış

İki ayrı bilgisayar konuşur:
- **Yer istasyonu (ESP32):** GPS + alıcı kimliğini paketler, LoRa ile gönderir.
- **İHA (Jetson Orin Nano):** paketi alır, **Pixhawk**'a (ArduCopter) MAVLink
  ile komut vererek otonom kalkış/rota/iniş yaptırır; kameradan ArUco ve yüz
  işler.

```
ESP32 ──LoRa 433MHz──► Jetson ──MAVLink(UART)──► Pixhawk ──► motorlar/servo
(GPS,buton)            (kamera, ArUco, yüz, karar)
```

Yazılımın iki çalışma modu vardır, `KOKPIT_SIM` ortam değişkeniyle seçilir:
- `KOKPIT_SIM=1` → simülasyon (SITL veya yazılım fiziği), **uçuş yok**.
- `KOKPIT_SIM=0` → gerçek donanım.

---

## 2. Gereken donanım ve yazılım

### Donanım (rapordan)
| Katman | Parça |
|--------|-------|
| Uçuş kontrol | Pixhawk 2.4.8 (ArduCopter 4.x) |
| Görev bilgisayarı | NVIDIA Jetson Orin Nano |
| GPS (İHA) | Holybro M9N |
| Lidar | Benewake TFS20 |
| Kamera | WaveShare IMX219 (CSI) |
| Haberleşme | 2× LoRa E32 433 MHz |
| Yer istasyonu | ESP32 (TTGO T-Display), NEO-M8N GPS, OV5640, buton |
| Yük bırakma | PWM servo |
| Güç | 6S 7000mAh LiPo, Matek PDB |

### Yazılım
- Jetson: JetPack (Ubuntu), Python 3.8+, OpenCV (contrib/aruco), pymavlink,
  face_recognition (dlib), pyserial.
- PC (geliştirme/test): aynı Python paketleri + ArduPilot SITL (opsiyonel).
- ESP32: Arduino IDE + TinyGPSPlus + TFT_eSPI.

---

## 3. Kurulum

### 3.1 Jetson Orin Nano (İHA görev bilgisayarı)

```bash
# Depoyu Jetson'a kopyala, içine gir
cd enesihayarisma

# Sistem paketleri
sudo apt update
sudo apt install -y python3-pip python3-opencv cmake build-essential

# Python paketleri
pip3 install pymavlink pyserial numpy

# OpenCV: JetPack'te genelde kuruludur (CUDA'lı). Kontrol:
python3 -c "import cv2; print(cv2.__version__, hasattr(cv2,'aruco'))"
#   -> True değilse:  pip3 install opencv-contrib-python

# face_recognition (dlib derler — UZUN sürer, swap aç!)
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && \
  sudo mkswap /swapfile && sudo swapon /swapfile
pip3 install dlib face_recognition
```

> Not: `face_recognition` kurulamazsa kod otomatik olarak hafif bir OpenCV
> yedeğine düşer (sadece test için). Demo öncesi gerçek kütüphaneyi kur.

UART izni (Pixhawk/LoRa seri portları için):
```bash
sudo usermod -aG dialout $USER     # sonra çıkış-giriş yap
```

### 3.2 PC'de geliştirme/test (opsiyonel)
```bash
pip install -r requirements.txt
KOKPIT_SIM=1 python3 -m pytest tests/ -q      # 26 test geçmeli
cd sitl && KOKPIT_SIM=1 python3 software_demo.py
```

### 3.3 ESP32 yer istasyonu
1. Arduino IDE → **ESP32 board paketi** kur (Boards Manager → "esp32").
2. Library Manager → **TinyGPSPlus** ve **TFT_eSPI** kur.
3. TTGO T-Display için TFT_eSPI `User_Setup_Select.h` içinde TTGO profilini seç.
4. `firmware/esp32_ground_station/ground_station.ino` ve `packet_protocol.h` aynı klasörde olsun.
5. Board = "TTGO LoRa32 / ESP32 Dev Module", doğru COM portu → **Upload**.

---

## 4. Kablolama

### 4.1 İHA tarafı

**Pixhawk ↔ Jetson (TELEM2 ↔ Jetson UART):**
| Pixhawk TELEM2 | Jetson Orin Nano (40-pin) |
|----------------|---------------------------|
| TX | RX (pin 10, /dev/ttyTHS1) |
| RX | TX (pin 8) |
| GND | GND |

> Ortak GND şart. Seviye 3.3V (uyumlu). `config.py` → `mavlink_real="/dev/ttyTHS1"`,
> baud 921600.

**LoRa E32 ↔ Jetson (USB-UART dönüştürücü ile en kolay):**
- E32 TX/RX/GND → USB-TTL → Jetson USB (`/dev/ttyUSB0`, 9600 baud).
- E32: M0=GND, M1=GND (şeffaf mod).

**Benewake TFS20 Lidar → Pixhawk** (serial veya I2C; ArduPilot RNGFND).
**IMX219 → Jetson CSI** konnektörü (CAM0).
**Drop servo → Pixhawk AUX OUT 1** (= SERVO9), ayrı 5V BEC ile besle.

### 4.2 Yer istasyonu (ESP32)
`firmware/esp32_ground_station/README.md` içindeki pin tablosuna bak. Özet: GPS→UART1,
LoRa→UART2 (+M0/M1/AUX), buton→GPIO33, buzzer→GPIO32.

> İki E32 modülünün **adres/kanal/hava hızı** ayarları AYNI olmalı, yoksa
> haberleşmezler.

---

## 5. ArduPilot / Pixhawk parametreleri

Mission Planner / QGroundControl ile bağlan, şu parametreleri ayarla.
(Değerleri kendi donanımına göre doğrula; bunlar başlangıç önerisidir.)

### 5.1 Companion (Jetson) bağlantısı
```
SERIAL2_PROTOCOL = 2      # MAVLink2 (TELEM2 = Jetson)
SERIAL2_BAUD     = 921    # 921600
```

### 5.2 Drop servo (AUX1 = SERVO9)
```
SERVO9_FUNCTION  = 0      # Disabled -> MAVLink DO_SET_SERVO ile kontrol edilebilir
SERVO9_MIN       = 1100   # config DropperConfig.pwm_locked ile uyumlu
SERVO9_MAX       = 1900   # config DropperConfig.pwm_released ile uyumlu
```
> Kod kanal numarasını `config.py` → `DropperConfig.servo_channel = 9`'dan alır.

### 5.3 Lidar (Benewake TFS20)
```
RNGFND1_TYPE     = <Benewake tipi>   # serial için ArduPilot dokümanından doğrula
RNGFND1_MIN_CM   = 10
RNGFND1_MAX_CM   = 1200
RNGFND1_ORIENT   = 25                # aşağı bakan
```

### 5.4 Failsafe (KRİTİK — yazılımın failsafe'i bunların yerine geçmez, tamamlar)
```
FENCE_ENABLE     = 1
FENCE_TYPE       = 3      # daire + irtifa
FENCE_RADIUS     = 150    # config SafetyConfig.geofence_radius_m ile uyumlu
FENCE_ALT_MAX    = 30     # config SafetyConfig.geofence_max_alt_m ile uyumlu
FENCE_ACTION     = 1      # RTL
BATT_LOW_VOLT    = 21.6   # config battery_warn_voltage
BATT_CRT_VOLT    = 20.4   # config battery_critical_voltage
BATT_FS_LOW_ACT  = 2      # RTL
BATT_FS_CRT_ACT  = 1      # LAND (veya RTL)
FS_THR_ENABLE    = 1      # RC kaybı -> RTL
FS_GCS_ENABLE    = 1      # GCS/companion kaybı -> RTL
RTL_ALT          = 1500   # cm (15 m)
WPNAV_SPEED      = 500    # cm/s (5 m/s), config cruise_speed_ms ile uyumlu
```

### 5.5 GUIDED hız komutları
Varsayılanlar yeterlidir; kod `SET_POSITION_TARGET_*` ile hem global hedef hem
gövde-çerçevesi hız gönderir. Ek ayar gerekmez. (İstersen `GUID_OPTIONS`'ı
inceleyebilirsin.)

> **Önemli:** `config.py` ile ArduPilot parametrelerini **tutarlı** tut. İkisi
> çelişirse en kısıtlayıcı olan (genelde ArduPilot) devreye girer.

---

## 6. Kalibrasyon

### 6.1 Kamera kalibrasyonu (poz doğruluğu için)
9x6 satranç tahtası yazdır (kare ~25 mm), sonra:
```bash
cd tools
python3 calibrate_camera.py --live --cols 9 --rows 6 --square 0.025
# BOŞLUK ile ~20 kare çek (farklı açı/uzaklık), q ile bitir
# -> camera_calibration.npz üretir
mv camera_calibration.npz ../onboard/      # aruco_detector otomatik yükler
```
Yapılmazsa config'teki kaba varsayılanlar kullanılır (poz daha az doğru olur).

### 6.2 ArUco marker yazdırma
```bash
python3 tools/generate_aruco.py --id 0 --dict DICT_5X5_100 --size 1000 --out ped_marker.png
```
- `--id` ve `--dict`, `config.py` → `ArucoConfig.target_id` / `dictionary` ile aynı olmalı.
- Yazdırınca **fiziksel kenar uzunluğunu** ölç ve `ArucoConfig.marker_length_m`'e
  yaz (örn. 0.30 m). Bu değer yanlışsa poz/mesafe yanlış çıkar.
- Marker çevresinde beyaz "quiet zone" bırak (script otomatik ekler).

### 6.3 Servo PWM ayarı (paket bırakma)
Pervanesiz, masa testinde:
```bash
cd drone
KOKPIT_SIM=0 python3 -c "
from mavlink_interface import DroneController
from package_dropper import PackageDropper
d=DroneController(); d.connect()
pd=PackageDropper(d)
pd.lock();  input('kilitli mi? Enter...')
pd.drop();  input('açıldı/bıraktı mı? Enter...')
d.close()"
```
Paketi tutmuyor/açmıyorsa `DropperConfig.pwm_locked` / `pwm_released` değerlerini
ayarla (1000–2000 arası).

### 6.4 Görsel servo işaret (sign) kalibrasyonu — ÖNEMLİ
İlk hassas yaklaşma denemesinde İHA marker'a doğru değil **ters** yöne kaçarsa,
`onboard/visual_servo.py` başındaki işaretleri çevir:
```python
FWD_SIGN = 1.0     # ileri/geri ters ise -1.0 yap
RIGHT_SIGN = 1.0   # sağ/sol ters ise -1.0 yap
```
Bu, kameranın montaj yönüne bağlıdır. Önce **SITL + sim kamera** ile, sonra çok
düşük irtifada elle gözeterek doğrula.

### 6.5 PID kazanç ayarı
`config.py` → `PIDConfig`. Konservatif başla (varsayılanlar öyle):
`kp_xy=0.6, ki_xy=0.05, kd_xy=0.20`. Salınım olursa `kp`'yi düşür; yavaş
merkezleniyorsa kademeli artır. `max_xy_speed_ms` ve `max_z_speed_ms`
güvenlik tavanlarıdır — küçük tut.

---

## 7. Yüz veri seti hazırlama
- Her yetkili alıcı için: `faces/alici_<id>.jpg` (id = ESP32'nin gönderdiği
  `recipient_id`).
- Net, önden, iyi ışıkta, yüz kareyi dolduran foto. Demo ışığına yakın çek.
- Eşik/oylama: `config.py` → `FaceConfig` (`match_distance_threshold=0.45`,
  `votes_required=5`, `votes_needed_to_pass=3`). Çok katı/gevşekse ayarla.
- Detay: `faces/README.md`.

---

## 8. Test (3 katman)

Her zaman bu sırayla ilerle; bir katman geçmeden sonrakine geçme.

**Katman 1 — yazılım demosu (kurulumsuz):**
```bash
cd sitl
KOKPIT_SIM=1 python3 software_demo.py            # başarılı teslimat
KOKPIT_SIM=1 python3 software_demo.py --reject    # biyometrik ret
KOKPIT_SIM=1 python3 software_demo.py --save-video # logs/demo.mp4
```

**Katman 2 — otomatik testler:**
```bash
KOKPIT_SIM=1 python3 -m pytest tests/ -q          # 26 passed beklenir
```

**Katman 3 — gerçek ArduPilot SITL:**
```bash
cd sitl
./run_sitl.sh                                      # Terminal 1
KOKPIT_SIM=1 python3 test_mission_sitl.py          # Terminal 2
```
SITL kurulumu: `simulation/README.md`.

**Sonra donanım:** pervanesiz masa testi → tethered/Loiter elle uçuş →
geniş sahada ilk otonom deneme.

---

## 9. Saha operasyon prosedürü

### 9.1 Uçuş öncesi (yerde)
1. Bataryayı tak, **pervaneleri en son tak**.
2. Jetson'ı başlat, kamera/LoRa portlarını kontrol et:
   ```bash
   ls /dev/ttyTHS1 /dev/ttyUSB0     # var mı?
   ```
3. GCS (Mission Planner) ile telemetriden bağlan; GPS fix (≥8 uydu, HDOP<1.5),
   EKF yeşil, batarya dolu mu?
4. Geofence/failsafe parametreleri yüklü mü? (Bölüm 5.4)
5. Drop mekanizması **kilitli** ve paket takılı mı?
6. Pervaneleri tak, çevreyi boşalt, pilot kill-switch hazır.

### 9.2 Görevi başlat
İHA tarafında:
```bash
cd drone
KOKPIT_SIM=0 python3 mission.py
```
Yazılım "Yer istasyonundan teslimat talebi bekleniyor..." der.

### 9.3 Tetikleme (yer istasyonu)
- ESP32 ekranında GPS fix'i bekle (yeşil).
- Doğru alıcı kimliğini seç (uzun basışla değiştir).
- **Kısa basış** → paket gönderilir. İHA otonom kalkar.

### 9.4 Görev sırasında izleme
GCS'te modu/irtifayı izle. İHA: kalkış → hedefe rota → arama → hassas yaklaşma
(2.5 m) → yüz doğrulama → (doğruysa) bırakma → RTL → iniş → disarm.
Anormallik görürsen **moda elle müdahale et / kill-switch** kullan.

### 9.5 Uçuş sonrası
- Disarm olduğunu doğrula. Bataryayı çıkar.
- `logs/` ve ArduPilot dataflash loglarını incele.

---

## 10. Parametre referansı (config.py)

Tümü `onboard/config.py` içinde, gruplar halinde. En sık dokunulanlar:

| Parametre | Varsayılan | Anlamı |
|-----------|-----------|--------|
| `FlightConfig.takeoff_altitude_m` | 8.0 | kalkış tırmanma irtifası |
| `FlightConfig.cruise_altitude_m` | 15.0 | hedefe gidiş irtifası |
| `FlightConfig.cruise_speed_ms` | 5.0 | seyir hızı |
| `FlightConfig.search_altitude_m` | 10.0 | marker arama irtifası |
| `FlightConfig.drop_altitude_m` | 2.5 | **paket bırakma irtifası (2–3 m)** |
| `FlightConfig.center_tolerance_m` | 0.15 | merkezleme kabul hatası |
| `ArucoConfig.marker_length_m` | 0.30 | **marker fiziksel kenarı (ölç!)** |
| `ArucoConfig.target_id` | 0 | ped marker ID |
| `PIDConfig.kp_xy/ki_xy/kd_xy` | 0.6/0.05/0.20 | görsel servo kazançları |
| `PIDConfig.descent_speed_ms` | 0.4 | merkezliyken alçalma hızı |
| `PIDConfig.max_xy_speed_ms` | 1.5 | yatay hız tavanı (güvenlik) |
| `PIDConfig.max_z_speed_ms` | 0.6 | dikey hız tavanı (güvenlik) |
| `FaceConfig.match_distance_threshold` | 0.45 | yüz eşleşme katılığı (küçük=katı) |
| `FaceConfig.votes_needed_to_pass` | 3 | kaç karede eşleşme gerekir |
| `DropperConfig.servo_channel` | 9 | AUX1 = SERVO9 |
| `DropperConfig.pwm_locked/released` | 1100/1900 | servo kapalı/açık |
| `SafetyConfig.battery_critical_voltage` | 20.4 | kritik batarya → RTL |
| `SafetyConfig.min_satellites` | 8 | arm için min uydu |
| `SafetyConfig.geofence_radius_m` | 150 | yatay sınır |
| `SafetyConfig.geofence_max_alt_m` | 30 | irtifa sınırı |

`python3 onboard/config.py` çalıştırınca aktif değerleri ve `validate()`
sonucunu yazdırır.

---

## 11. Görev akışı — durum durum

`onboard/state_machine.py` + `onboard/mission.py`:

| Durum | Ne yapar | Başarısızlıkta |
|-------|----------|----------------|
| WAIT_PACKET | LoRa'dan geçerli (GPS fix'li) teslimat paketi bekler | — |
| TAKEOFF | pre-arm kontrol + GUIDED + arm + VTOL kalkış | ABORT |
| NAVIGATE | hedef GPS'e `goto`, kabul yarıçapına kadar | timeout → ABORT |
| SEARCH_MARKER | arama irtifasına in, ArUco tara | bulunmazsa **sarmal arama**, yine yoksa RTL |
| PRECISION_APPROACH | PID ile merkezle + 2.5 m'ye alçal | marker kaybı→sarmal; başarısız→RTL |
| BIOMETRIC_VERIFY | hover'da yüz oylaması | eşleşmezse **teslimat askıya → RTL** |
| DROP_PACKAGE | servo aç, paket bırak, biraz yüksel | — |
| RETURN_HOME | RTL | LANDING'e düşer |
| LANDING | LAND, iniş bekle | — |
| DISARM | motor kapat, mekanizmayı kilitle | MISSION_COMPLETE |
| ABORT | RTL/LAND ile güvenli sonlandır | — |

Arka planda **failsafe izleyici** her 0.5 sn: link, kritik batarya, geofence
(yarıçap/irtifa) denetler; ihlalde ABORT tetikler.

---

## 12. Sorun giderme

| Belirti | Olası neden / çözüm |
|---------|---------------------|
| "Heartbeat alınamadı" | TELEM2 kablosu/baud (921600), SERIAL2_PROTOCOL=2, ortak GND |
| Arm olmuyor | GPS fix<3D, uydu<8, HDOP>1.5, EKF kırmızı, pre-arm hatası (GCS'te oku) |
| Kalkış yok | GUIDED'a geçemiyor; mode_mapping/RC failsafe; ArduPilot arming check |
| Marker görülmüyor | irtifa çok yüksek (marker piksel<14), kötü ışık, yanlış `dictionary`/`target_id`, kalibrasyon |
| İHA marker'dan kaçıyor | `visual_servo.FWD_SIGN/RIGHT_SIGN` işaretlerini çevir (6.4) |
| Salınım/oynama | PID `kp_xy` yüksek; düşür. Titreşim/EKF için frame/damping |
| Mesafe/poz yanlış | `marker_length_m` yanlış veya kamera kalibre değil (6.1/6.2) |
| Yüz hep FAIL | `faces/alici_<id>.jpg` yok/yanlış id, kötü foto, eşik çok katı (`match_distance_threshold`'u 0.5'e çıkar) |
| Paket düşmüyor | SERVO9_FUNCTION=0 değil; PWM değerleri; servo beslemesi (BEC) |
| LoRa paket gelmiyor | iki E32 ayarı farklı; M0/M1≠0; baud≠9600; anten yok; CRC hatası (log: `crc_errors`) |
| face_recognition yok uyarısı | `pip install face_recognition`; yoksa sadece OpenCV yedeği (test) çalışır |

Loglar: çalışırken konsol çıktısı + ArduPilot dataflash (.bin) logları en
değerli kaynaktır.

---

## 13. Acil durum ve güvenlik

- **Her zaman** kill-switch'li bir RC verici ve uyanık bir pilot bulunsun.
- İlk otonom uçuşu **geniş, boş, izinli** sahada yap.
- ArduPilot failsafe'leri (Bölüm 5.4) **bağımsız** güvenlik ağıdır; yazılım
  çökse bile RTL/LAND yapar. Mutlaka yüklü ve test edilmiş olsun.
- Yazılım güvenlik katmanları: hız komutu kırpma, geofence izleme, batarya/
  link/uydu failsafe, zaman aşımları, marker kaybında yerinde tutunma,
  biyometrik başarısızlıkta teslimatı askıya alma.
- Paket bırakma irtifası **2.5 m** (config) — 2–3 m şartına uygun, `validate()`
  ile denetlenir.
- Pervaneleri yalnızca test bittikten ve alan boşaldıktan sonra tak.

---

## 14. Yarışma günü hızlı kontrol kartı

```
[ ] Batarya dolu, sağlam; yedek batarya hazır
[ ] Jetson açık; /dev/ttyTHS1 ve /dev/ttyUSB0 görünüyor
[ ] Mission Planner bağlı; GPS≥8 uydu, HDOP<1.5, EKF yeşil
[ ] Failsafe + geofence parametreleri yüklü (Bölüm 5.4)
[ ] camera_calibration.npz yerinde; marker doğru ID/ölçü
[ ] faces/alici_<id>.jpg hazır; eşik test edildi
[ ] Drop mekanizması kilitli, paket takılı
[ ] visual_servo işaretleri SITL'de doğrulandı
[ ] software_demo + pytest + SITL testleri geçti
[ ] Pervaneler takıldı, alan boş, pilot + kill-switch hazır
[ ] İHA tarafı:  KOKPIT_SIM=0 python3 mission.py
[ ] Yer istasyonu: GPS fix bekle -> alıcı seç -> kısa basış
[ ] Görevi GCS'ten izle; gerekirse elle müdahale
```

İyi uçuşlar — ve dron düşmesin. 🚁
