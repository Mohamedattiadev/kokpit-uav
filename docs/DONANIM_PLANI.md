# DONANIM_PLANI.md — Donanım Tarafı Yapılacaklar (Full Detay)

> **Amaç:** Donanım ekibi bu belgeye bakarak hiçbir karar verme yükü olmadan,
> sadece adımları sırayla uygulayarak işi bitirebilmeli. Her madde için:
> ne lazım, nasıl bağlanır, hangi komut, nasıl doğrulanır, hata olursa ne yapılır.
>
> Yazılım tarafı (Jetson Python kodu + ESP32 TX firmware'i) tamamen hazır
> (`make test` 203 yeşil, CI yeşil). Aşağıdaki dört iş bitince saha
> testlerine hazırız.

---

## İçindekiler

1. [İŞ-1 — Jetson Orin Nano Kurulum + TensorRT Yüz Tanıma Engine Build](#i̇ş-1)
2. [İŞ-2 — Kamera + Lidar Extrinsics Kalibrasyon](#i̇ş-2)
3. [İŞ-3 — ESP32 Yer İstasyonu RX Parser Firmware'i](#i̇ş-3)
4. [İŞ-4 — ArduCopter Param Yükleme + Saha Test Uçuşları](#i̇ş-4)
5. [Genel Sorun Giderme + Kontak Listesi](#genel-sorun-giderme)

---

<a id="i̇ş-1"></a>
## İŞ-1 — Jetson Orin Nano Kurulum + TensorRT Engine Build

**Sorumlu:** Donanım ekibi (Jetson + yapay zeka tarafı)
**Tahmini Süre:** İlk sefer 4-6 saat (JetPack flash dahil); tekrar ~30 dk
**Önkoşul:** Jetson Orin Nano Developer Kit + 64 GB+ NVMe SSD + JetPack 6.0+ flash edilmiş

### Neden Yapılıyor

Rapor (884462.pdf) bölüm 2.1.2 ve 3.3.1.2 şunu söz veriyor:

> "TensorRT destekli Evrişimli Sinir Ağları (CNN) ile alıcının yüzü gerçek
> zamanlı tanınır."

Şu an yazılım `face_recognition` (dlib, CPU) ile fallback çalışıyor; bu
modda Jetson'da 1-2 FPS, biyometrik doğrulama hover sırasında 8-10 saniye
sürüyor. TensorRT FP16 ile bu süre <1 saniyeye iner ve rapor taahhüdü
yerine gelir.

### Malzeme Listesi

| # | Parça | Adet | Not |
|---|---|---|---|
| 1 | Jetson Orin Nano Developer Kit | 1 | 8GB RAM modeli |
| 2 | NVMe SSD (64 GB+) | 1 | Sistem + model deposu |
| 3 | microSD (64 GB) | 1 | Yedek + ilk flash |
| 4 | Soğutma fanı + heatsink | 1 | Dev Kit ile gelir |
| 5 | DC power supply 19V 3A | 1 | Resmi adaptör |
| 6 | USB-C kablo (host PC bağlantısı için) | 1 | Flash sırasında |
| 7 | Ethernet kablosu | 1 | Model indirme için |
| 8 | HDMI monitör + klavye + mouse | 1 | İlk kurulum |

### Adım 1.1 — JetPack 6.0+ Flash

NVIDIA SDK Manager kullanılacak. Host PC: Ubuntu 22.04 LTS gerekli.

```bash
# Host PC üzerinde:
# 1) SDK Manager kur (NVIDIA hesabı gerekir)
# https://developer.nvidia.com/sdk-manager
# .deb paketi indir + kur:
sudo dpkg -i sdkmanager_*.deb
sudo apt-get install -f

# 2) Jetson'ı recovery moduna al:
#    - FC (Force Recovery) butonuna bas ve basılı tut
#    - Power butonuna bas
#    - 2 saniye sonra FC butonunu bırak

# 3) USB-C ile host PC'ye bağla, sdkmanager'ı başlat:
sdkmanager

# 4) Arayüzde:
#    - Target: Jetson Orin Nano
#    - JetPack: 6.0 (veya en güncel 6.x)
#    - Components: tümünü işaretle (CUDA, cuDNN, TensorRT, OpenCV vs.)
#    - Storage: NVMe SSD (microSD kullanma)
#    - Flash başlat (~30 dk)

# 5) Flash bitince Jetson reboot olur. İlk açılışta kullanıcı oluştur:
#    Username: kokpit  Password: <takım kararı>  Hostname: kokpit-jetson
```

### Adım 1.2 — Sistem Hazırlığı

Jetson terminal:

```bash
# Sistemi güncelle
sudo apt-get update && sudo apt-get upgrade -y

# Performans modu (15W max, fan auto)
sudo nvpmodel -m 0
sudo jetson_clocks

# JetPack sürüm kontrolü (6.0+ olmalı)
sudo apt-cache show nvidia-jetpack | head -3

# TensorRT versiyon kontrolü
dpkg -l | grep -i tensorrt
# Beklenen: nvinfer 8.6 veya üzeri

# Python TRT binding
python3 -c "import tensorrt; print(tensorrt.__version__)"
# Beklenen: 8.6.x veya 10.x

# Swap aç (8GB) — model derleme için kritik
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
free -h   # 8G swap görünmeli
```

### Adım 1.3 — Repo Clone + Bağımlılık Kurulumu

```bash
cd /opt
sudo git clone https://github.com/Mohamedattiadev/kokpit-uav
sudo chown -R kokpit:kokpit kokpit-uav
cd kokpit-uav

# Python venv
python3 -m venv .venv
source .venv/bin/activate

# Bağımlılıklar (face_recognition dahil — dlib derler, ~20 dk)
pip install --upgrade pip
pip install -r requirements.txt
pip install sdnotify pyyaml pycuda

# Test (203 geçmeli, ~2 dk)
KOKPIT_SIM=1 make test
```

### Adım 1.4 — InsightFace Modelleri İndir

ArcFace R50 + RetinaFace MobileNet 0.25 ONNX modelleri InsightFace
`buffalo_l` paketinden gelir.

```bash
cd /opt/kokpit-uav
mkdir -p onboard/models/onnx

# Otomatik indirme (insightface yoksa pip install insightface)
pip install insightface onnxruntime

python3 <<'EOF'
import insightface
# buffalo_l: arcface_r50.onnx + retinaface MnetV0.25
app = insightface.app.FaceAnalysis(name='buffalo_l', root='/opt/kokpit-uav/onboard/models')
app.prepare(ctx_id=0)
print("Modeller indirildi:", app.models.keys())
EOF

# Modeller şuraya iner:
# /opt/kokpit-uav/onboard/models/models/buffalo_l/det_500m.onnx
# /opt/kokpit-uav/onboard/models/models/buffalo_l/w600k_r50.onnx
```

### Adım 1.5 — TensorRT Engine Build

```bash
cd /opt/kokpit-uav
source .venv/bin/activate

python3 tools/build_face_trt.py \
    --detector onboard/models/models/buffalo_l/det_500m.onnx \
    --embedder onboard/models/models/buffalo_l/w600k_r50.onnx \
    --out onboard/models \
    --precision fp16

# Süre: ~10-15 dk (her engine için).
# Beklenen çıktı:
#   [TRT] yazıldı: onboard/models/det_8.6.1_<jetpack>_fp16.engine
#   [TRT] yazıldı: onboard/models/emb_8.6.1_<jetpack>_fp16.engine
#   onboard/models/.meta.json
```

### Adım 1.6 — TRT Backend Doğrulama

```bash
# Smoke test
ls onboard/models/*.engine
# det_*.engine + emb_*.engine olmalı

# Test runner skip yerine geçmeli
KOKPIT_SIM=1 python3 -m pytest tests/test_face_trt.py -v
# test_trt_engine_load_smoke artık PASS olmalı (skip değil)

# Force backend smoke
python3 <<'EOF'
import sys; sys.path.insert(0, 'onboard')
from face_verifier import FaceVerifier
v = FaceVerifier(force_backend="trt")
print("Backend:", v.backend_name)
# Beklenen: "tensorrt"
EOF
```

### Adım 1.7 — systemd Servis Aktif Et

```bash
cd /opt/kokpit-uav
sudo cp systemd/kokpit-mc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kokpit-mc
sudo systemctl start kokpit-mc

# Log izle
journalctl -u kokpit-mc -f
# WATCHDOG=1 + paket log'ları görünmeli
```

### Doğrulama Checklist'i — İŞ-1

- [ ] `nvpmodel -q` → MAXN veya 15W
- [ ] `python3 -c "import tensorrt; print(tensorrt.__version__)"` → 8.6+
- [ ] `ls onboard/models/*.engine` → det + emb engine'ler mevcut
- [ ] `pytest tests/test_face_trt.py` → 6 PASS (skip yok)
- [ ] `FaceVerifier(force_backend="trt").backend_name == "tensorrt"`
- [ ] `systemctl status kokpit-mc` → active (running)

### Sorun Giderme — İŞ-1

| Sorun | Sebep | Çözüm |
|---|---|---|
| `sdkmanager` Jetson görmüyor | Recovery mode yanlış | FC tutarak power'a bas |
| `tensorrt import` ImportError | Python venv sistem TRT'sini görmüyor | `--system-site-packages` ile venv oluştur |
| Engine build OOM | Swap kapalı | 1.2'deki swap adımı |
| `dlib` derleme hatası | gcc/cmake eksik | `sudo apt install build-essential cmake libopenblas-dev` |
| Engine yüklendi ama TRT çağrısı segfault | pycuda + JetPack uyumsuz | `pip install pycuda==2024.1` |

---

<a id="i̇ş-2"></a>
## İŞ-2 — Kamera + Lidar Extrinsics Kalibrasyon

**Sorumlu:** Mekanik + elektronik ekibi
**Tahmini Süre:** 1-2 saat (her sensör değişiminde tekrarlanır)
**Önkoşul:** Drone gövdesi tamamlanmış, kamera + lidar fiziksel olarak monte edilmiş

### Neden Yapılıyor

Kamera ve lidar drone gövde merkezinden uzakta monte edilir (genelde
5-15 cm öne/aşağı). Yazılım, bu offset'i bilmeden naif sensör verisini
doğrudan kontrolcüye beslese hassas iniş 5-10 cm yana kayar. Rapor
hedefi ±14 cm; bu kalibrasyon yapılmadan hedef tutmak zor.

### Malzeme Listesi

| # | Parça | Adet | Not |
|---|---|---|---|
| 1 | Şerit metre (cm hassas) | 1 | 2 m yeterli |
| 2 | Dijital açıölçer | 1 | Pitch/roll için (opsiyonel) |
| 3 | Su terazisi | 1 | Drone'u düz zemine koymak için |
| 4 | Pencil + not defteri | 1 | Ölçüleri yaz |

### Koordinat Sistemi (Hatırlatma)

Drone gövde çerçevesi (rapor + ArduCopter standart):

```
              x (+ ileri = burun yönü)
              ↑
              │
              │
   y ←────────┼────────→ y (+ sağ)
              │
              │
              ↓
              z (+ aşağı)
```

### Adım 2.1 — Drone'u Düz Yere Koy

- Su terazisi ile gövdenin yatay olduğunu doğrula
- Burun yönünü (x+) referans al — duvardaki bir noktaya bak

### Adım 2.2 — Kamera Offset Ölç

Gövdenin **geometrik merkezi** referans nokta. Bu nokta genelde Pixhawk'ın
tam altıdır.

| Eksen | Nasıl ölçülür |
|---|---|
| `cam.x` | Pixhawk altından kamera lensinin merkezine kadar **ileri** yönde uzaklık (m). Lens önde ise +, arkada ise −. |
| `cam.y` | Sağa kayma. Sağda ise +, solda ise −. |
| `cam.z` | Lens **aşağıda** olduğu için pozitif. Pixhawk seviyesinden lensin alt yüzeyine kadar metre. |
| `cam.roll/pitch/yaw` | Lens tam aşağı bakıyorsa 0,0,0. Hafif eğikse açıölçer ile derece olarak ölç. |

Örnek değer (ZD550 frame için tahmini): `x=0.00, y=0.00, z=0.10`

### Adım 2.3 — Lidar Offset Ölç

| Eksen | Nasıl ölçülür |
|---|---|
| `lidar.x` | Pixhawk altından lidar sensörünün ön yüzeyine ileri uzaklık |
| `lidar.y` | Sağa kayma |
| `lidar.z` | Sensörün ışın çıkış noktasının aşağı uzaklığı |

Örnek (TFmini Plus altta, hafif önde): `x=0.05, y=0.00, z=0.05`

### Adım 2.4 — Kalibrasyon Aracını Çalıştır

Jetson terminal:

```bash
cd /opt/kokpit-uav
source .venv/bin/activate

python3 tools/calibrate_extrinsics.py
# Soru soracak, ölçüleri sırayla gir:
# CAM x (ileri) [0.0]: 0.00
# CAM y (sağ) [0.0]: 0.00
# CAM z (aşağı) [0.1]: 0.10
# ...
# Tamamlanınca onboard/configs/extrinsics.yaml yazılır
```

### Adım 2.5 — Doğrulama

```bash
# Yaml içeriği kontrol et
cat onboard/configs/extrinsics.yaml

# Yazılımın doğru okuduğunu test et
python3 <<'EOF'
import sys; sys.path.insert(0, 'onboard')
from extrinsics import load_extrinsics
e = load_extrinsics()
print("Cam offset (x, y, z):",
      e.cam_to_body.x, e.cam_to_body.y, e.cam_to_body.z)
print("Lidar offset (x, y, z):",
      e.lidar_to_body.x, e.lidar_to_body.y, e.lidar_to_body.z)
EOF

# Test suite hâlâ yeşil olmalı
KOKPIT_SIM=1 pytest tests/test_extrinsics.py -v
```

### Doğrulama Checklist'i — İŞ-2

- [ ] Drone su terazisi ile düz konumda ölçüldü
- [ ] Tüm ölçüler **metre** cinsinden girildi (cm değil!)
- [ ] `onboard/configs/extrinsics.yaml` dosyası oluştu
- [ ] `load_extrinsics()` doğru değerleri okuyor
- [ ] Bir sonraki uçuş testinde marker hassas iniş ±14 cm içinde

### Sorun Giderme — İŞ-2

| Sorun | Çözüm |
|---|---|
| YAML parse hatası | Negatif değerler için işaret unutma (`-0.05`); virgül değil nokta |
| İniş hâlâ kayıyor | Drone gövdesini tekrar düzeltip ölçü tekrar al; rüzgâr varsa kapalı alanda yap |
| Lidar değeri 0 m | Lidar bağlantısı (ARDUCOPTER RNGFND1_TYPE param) ayrı sorun, kalibrasyon değil |

---

<a id="i̇ş-3"></a>
## İŞ-3 — ESP32 Yer İstasyonu RX Parser Firmware'i

**Sorumlu:** Attia (firmware) + donanım ekibi
**Tahmini Süre:** 4-6 saat
**Önkoşul:** ESP32 yer istasyonu hazır, LoRa E32 modülü monte, TFT ekran çalışıyor

### Neden Yapılıyor

Drone, görev sırasında 1 Hz TELEMETRY paketi gönderiyor (mode, batarya,
faz, RSSI, paket kaybı). Şu an ESP32 sadece TX yapıyor — gelen paketi
parse edip TFT'de göstermiyor. Yarışma sahasında sinyal düşerse fark
edilmez. Bu firmware yamaşı şart.

### Malzeme Listesi

Yeni donanım gerekmiyor. Mevcut yer istasyonu:

- ESP32 DevKit
- LoRa E32-433T20D
- TFT ekran (TFT_eSPI uyumlu)
- NEO-M8N GPS
- Buton + buzzer

### Görev (Geliştiriciye Brief)

`firmware/esp32_ground_station/ground_station.ino` dosyasına aşağıdaki
özelliklerin eklenmesi:

1. LoRa UART'tan gelen bayt akışını **packet_protocol.h** ile parse et
   (CRC + AES + SHA doğrulaması).
2. `MSG_TELEMETRY` paketi gelirse içerikten (mode, batarya, faz, RSSI,
   loss) değerleri çıkar.
3. Bu değerleri TFT'de 2-3 satırlık bir bilgi alanında göster.
4. Sinyal kalitesi düştüğünde (loss > 30% veya RSSI < -100 dBm) buzzer
   ile uyar.

### Geliştirici İçin Prompt (Claude / başka AI'a ver)

> Aşağıdaki prompt'u yeni bir oturumda Claude Code'a yapıştır:

````
Sen kıdemli bir embedded yazılım mühendisisin. ESP32 (Arduino framework)
+ LoRa E32 + TFT_eSPI tecrübesi var.

Görev: kokpit-uav reposundaki ESP32 yer istasyonu firmware'ine
LoRa RX + TELEMETRY parser ekle.

Repo: https://github.com/Mohamedattiadev/kokpit-uav
Dosya: firmware/esp32_ground_station/ground_station.ino
Yardımcı: firmware/esp32_ground_station/packet_protocol.h
Protokol referansı: onboard/packet_protocol.py
Telemetri formatı (paket payload):
    <mode_id:u8><batt_mV:u16><phase:u8><rssi_dbm:i8><loss_pct:u8>
MsgType.TELEMETRY = 6

Mode ID eşleme (kokpit-uav onboard/telemetry_tx.py MODE_MAP):
    1=GUIDED, 2=AUTO, 3=LOITER, 4=RTL, 5=LAND,
    6=STABILIZE, 7=MANUAL, 8=BRAKE, 9=POSHOLD, 0=UNKNOWN

Yapacaklar:
1) packet_protocol.h içinde kokpit_pkt_parse() benzeri bir alıcı fonksiyon
   yaz (header magic, version, CRC16, AES-CCM decrypt, SHA doğrulama).
   Mevcut kokpit_pkt_build()'i ters çevir.
2) ground_station.ino loop() içinde LoraSerial.read() ile gelen baytı
   parser state machine'e besle (Jetson tarafındaki StreamParser'a paralel).
3) MSG_TELEMETRY parse edilince üç satırlık TFT bilgi alanı güncelle:
       Satır 1: MODE: GUIDED  BATT: 22.4V
       Satır 2: PHASE: NAVIGATE
       Satır 3: RSSI: -78 dBm  LOSS: 5%
4) loss > 30 || rssi < -100 ise buzzer kısa beep (her 3 sn).
5) packet_protocol.py içindeki replay LRU mantığını ESP32 tarafında da
   uygula (son 64 seq tut, tekrar gelirse drop).

Kurallar:
- Mevcut TX yolu (button → sendFaceDelivery) bozulmamalı.
- AES anahtarı zaten paylaşılıyor (kokpit_aes_init).
- Test: simulation/sim_backend.py içinden ESP32'ye seri paket enjekte
  edebilecek bir helper yaz, hem PC üzerinde hem ESP32'de loopback test.

Bitince: PR aç, başlık "feat: ESP32 RX parser + TELEMETRY display".
````

### Doğrulama Checklist'i — İŞ-3

- [ ] ESP32 RX parser eklendi, CRC + AES decrypt çalışıyor
- [ ] TFT 3 satır telemetri bilgisi gösteriyor
- [ ] Mock TELEMETRY paketi enjekte edildiğinde ekran güncelleniyor
- [ ] Loss > 30% veya RSSI < -100 dBm'de buzzer uyarı veriyor
- [ ] Mevcut button → face delivery hâlâ çalışıyor
- [ ] Loopback testte 100 paket %100 alınıyor

---

<a id="i̇ş-4"></a>
## İŞ-4 — ArduCopter Param Yükleme + Saha Test Uçuşları

**Sorumlu:** Zeki Emir (uçuş kontrolcüsü) + tüm takım
**Tahmini Süre:** 2 gün (yarım gün param + 1.5 gün uçuş kademe)
**Önkoşul:** İŞ-1, İŞ-2, İŞ-3 tamam; drone tam montajlı; batarya şarjlı

### Neden Yapılıyor

Yazılım uçuşa hazır. Şimdi ArduCopter parametre yüklemesi + manuel'den
otonoma kademeli geçiş şart. Bu yapılmadan otonom uçuş yapılırsa drone
düşer.

### Adım 4.1 — Mission Planner ile Param Yükle

1. Mission Planner aç → CONFIG → Full Parameter Tree
2. `ardupilot/` klasöründeki 7 param dosyasını sırayla yükle:

```
ardupilot/01_initial_setup.param      (frame class, motor count, vb.)
ardupilot/02_radio_calibration.param  (RC channel min/max)
ardupilot/03_battery_failsafe.param   (voltaj eşikleri)
ardupilot/04_geofence.param           (yarışma alanı sınırı)
ardupilot/05_compass_calibration.param
ardupilot/06_lidar_rangefinder.param  (TFmini RNGFND1 ayarları)
ardupilot/07_precland.param           (PRECLAND yerleşik PID)
```

3. Her yükleme sonrası **Write Params** + Pixhawk reboot

### Adım 4.2 — Kalibrasyon Turu (Saha Öncesi Zorunlu)

```
Sırayla:
1) Accelerometer cal (Mission Planner > Initial Setup > Accel)
2) Compass cal (8 yönlü döndürme)
3) Radio cal (RC stick min/max)
4) ESC cal (motor sırası + yön)
5) Lidar test (Mission Planner > Status > sonarrange canlı değişmeli)
6) Geofence test (RC ile manual'da sınıra yaklaş, RTL tetiklenmeli)
```

### Adım 4.3 — Kademeli Uçuş Testleri (Açık Alan)

**Her adımdan sonra başarısız olunursa dur, sebebi bulmadan ileri gitme.**

```
ADIM 1 — MANUAL hover
    Pilot stick ile 1 m hover, 30 sn. Tilt + drift normal mi?

ADIM 2 — STABILIZE hover
    Aynı uçuş STABILIZE modda. Otomatik leveling çalışıyor mu?

ADIM 3 — LOITER hover
    GPS hold testi. 1 dk hover, drift < 1 m olmalı.

ADIM 4 — RTL test
    LOITER'da kalkış, mod RTL'e al. Otomatik üsse dönüş + iniş.

ADIM 5 — GUIDED waypoint
    Mission Planner > Flight Plan > 50 m ileri waypoint.
    GUIDED + auto execute. Drone gider, gelir, iner.

ADIM 6 — Otonom görev (yazılım entry point)
    KOKPIT_SIM=0 python3 -m onboard.mission
    (veya systemd servisi)
    ESP32 buton bas → tam akış.
```

### Adım 4.4 — PID Tune (Saha)

Eğer Adım 3'te osilasyon varsa veya kontrol gevşek hissedilirse:

1. Mission Planner > CONFIG > Extended Tuning
2. AUTOTUNE channel atama (RC7 önerilen)
3. LOITER'da kalkış → AUTOTUNE switch → 5-10 dk uçuş
4. AUTOTUNE bitince LAND, Save Params

### Doğrulama Checklist'i — İŞ-4

- [ ] 7 ArduCopter param dosyası yüklü + Write Params yapıldı
- [ ] Compass + accel + radio + ESC kalibrasyonları tamam
- [ ] Lidar canlı veri veriyor
- [ ] Geofence ihlali → RTL tetikliyor
- [ ] Adım 1-5 tamamlandı, sorunsuz
- [ ] Otonom görev test uçuşu başarılı (5 ardışık deneme)
- [ ] Marker iniş ortalama hata < 20 cm

### Sorun Giderme — İŞ-4

| Sorun | Sebep | Çözüm |
|---|---|---|
| Toilet bowl (dairesel sallanma) | Compass kalibrasyon | 8 yönlü tekrar; metal uzaklaştır |
| GPS fix yok | Anten konumu | RC + GPS antenleri ayrı kollara |
| LOITER'da sürüklenme | GPS hatası yüksek | HDOP < 1.5 bekle, EKF reset |
| Otonom takeoff başlamıyor | Pre-arm fail | `STATUSTEXT` mesajını oku |
| Servo paket bırakmıyor | PWM eşiği yanlış | `SERVO9_FUNCTION=0 SERVO9_MIN=1100 MAX=1900` |

---

<a id="genel-sorun-giderme"></a>
## Genel Sorun Giderme + İletişim

### Yazılım Hatası Tespit Edilirse

1. `journalctl -u kokpit-mc -n 200` ile son log'lara bak
2. Hatayı GitHub Issues'a aç (`kokpit-uav` repo)
3. Yazılım tarafına bildir (Arda / Attia)

### Donanım Hatası Tespit Edilirse

1. Mission Planner > Messages sekmesinden Pixhawk hatasını oku
2. Drone dataflash log'unu indir (uçuştan sonra otomatik Jetson'da)
3. Donanım sorumlusu Zeki Emir'e ilet

### Acil Durum Protokolü (Uçuş Sırasında)

```
Pilot HER ZAMAN MANUAL stick'e müdahale edebilir.
1) Beklenmedik davranış → MODE switch'i STABILIZE'a al
2) Hâlâ kontrol edilemiyorsa → MOTOR KILL switch (RC7 high)
3) Drone yere düşerse → Pil bağlantısını ayır (yangın riski)
```

### Saha Test Öncesi Final Kontrol Listesi

- [ ] Batarya tam şarjlı (>24 V, 6S)
- [ ] Yedek batarya hazır
- [ ] Manual + Stabilize + Loiter + Guided modlar test edildi
- [ ] Geofence yüklü ve aktif
- [ ] Telemetri linki + RC link kontrol edildi
- [ ] Hava: rüzgâr < 5 m/s, yağmur yok
- [ ] Yarıçap 100 m içinde insan yok
- [ ] Yangın söndürücü hazır
- [ ] Pilot sertifikalı + dinlenmiş

---

## Zaman Çizelgesi (Tahmini)

| Hafta | İş | Sorumlu |
|---|---|---|
| Hafta 1 | İŞ-1 (Jetson + TRT) | Donanım ekibi |
| Hafta 1 | İŞ-2 (Extrinsics) | Mekanik |
| Hafta 2 | İŞ-3 (ESP32 RX) | Attia |
| Hafta 2-3 | İŞ-4 (Saha testleri) | Tüm takım |

Bu plan tamamlandığında **yarışmaya hazırız**.
