# Kokpit — Otonom Hassas Teslimat ve Biyometrik Doğrulamalı Lojistik İHA

Ankara Yıldırım Beyazıt Üniversitesi · Uluslararası İHA Yarışması · Serbest Görev

Bu depo, görevin **yazılım** tarafını içerir: yer istasyonundan (ped) gelen
dinamik GPS + alıcı kimliğiyle otonom kalkış yapan, hedefe rota oluşturup giden,
ArUco marker ile santimetre hassasiyetinde yaklaşan, alıcıyı yüz tanıma ile
doğrulayan ve doğruysa paketi 2–3 m'den bırakıp üsse dönen tam otonom döngü.

> **Durum:** Tüm pipeline yazılım fizik simülasyonunda **uçtan uca çalışır ve
> 26/26 otomatik test geçer** (gerçek ArUco tespiti + gerçek görsel servo PID ile).
> Gerçek uçuştan önce SITL ve donanım testleri zorunludur (bkz. Güvenlik).

> 📖 **Adım adım her şey için → [`docs/KILAVUZ.md`](docs/KILAVUZ.md)** (kurulum, kablolama,
> ArduPilot parametreleri, kalibrasyon, saha operasyonu, sorun giderme, yarışma
> günü kontrol kartı).
>
> 🗺️ **Yol haritası & açıklar → [`docs/PLAN.md`](docs/PLAN.md)** — denetimden çıkan tüm
> kritik bug + güvenlik açıkları + sprint planı (13 gün effort tahmini).
>
> ❓ **Takıma sorular → [`docs/QUESTIONS_FOR_TEAM.md`](docs/QUESTIONS_FOR_TEAM.md)** —
> mimari kararlar, yarışma alanı GPS, donanım envanteri.
>
> 🧠 **Spec / promptlar → [`docs/prompts/`](docs/prompts/)** — modül modül teknik prompt'lar
> (Claude Code ile geliştirme için).

---

## Takım görev dağılımı → dosya eşlemesi

| Üye | Sorumluluk (WhatsApp + rapor) | Kod |
|-----|------------------------------|-----|
| **Arda** | Otonom rota + hareket, ArUco tespiti, biyometrik eşleştirme, 2–3 m yaklaşma, paket bırakma | `onboard/mission.py`, `onboard/visual_servo.py`, `onboard/aruco_detector.py`, `onboard/face_verifier.py`, `onboard/package_dropper.py` |
| **Zeki Emir** | Veri paketi alınınca otonom kalkış | `onboard/autonomous_takeoff.py` |
| **Attia** | Yer istasyonu: GPS + yüz/alıcı paketleme ve LoRa ile gönderme (+ Arda'ya yardım) | `firmware/esp32_ground_station/ground_station.ino`, `firmware/esp32_ground_station/packet_protocol.h` |
| **Ortak** | LoRa paket protokolü, MAVLink köprüsü, config, testler | `onboard/packet_protocol.py`, `onboard/mavlink_interface.py`, `onboard/config.py`, `tests/` |

---

## Sistem mimarisi ve veri akışı

```
  YER İSTASYONU (Ped / ESP32)                       İHA
  ┌───────────────────────────┐         ┌──────────────────────────────────┐
  │ NEO-M8N GPS  ─┐           │  LoRa   │  LoRa E32 ──► lora_receiver.py     │
  │ OV5640 kamera │► ESP32 ───┼─433MHz─►│        (CRC doğrula, çöz)          │
  │ Buton (tetik) ┘  paketle  │         │            │                       │
  └───────────────────────────┘         │            ▼                       │
   (packet_protocol.h)                   │   mission.py  (durum makinesi)     │
                                         │            │                       │
   GPS + recipient_id  ─────────────────┤            ▼                       │
                                         │   autonomous_takeoff ─► NAVIGATE   │
                                         │            │                       │
                                         │            ▼                       │
                                         │   aruco_detector ─► visual_servo   │
                                         │     (IMX219 + PID, 2-3 m)          │
                                         │            │                       │
                                         │            ▼                       │
                                         │   face_verifier (biyometrik)       │
                                         │            │ PASS                  │
                                         │            ▼                       │
                                         │   package_dropper (servo PWM)      │
                                         │            │                       │
                                         │            ▼  RTL ─► LAND ─► DISARM │
                                         │   mavlink_interface ◄─► Pixhawk     │
                                         │        (pymavlink, ArduCopter)     │
                                         └──────────────────────────────────┘
```

Görev akışı (durum makinesi — `onboard/state_machine.py`):

```
WAIT_PACKET → TAKEOFF → NAVIGATE → SEARCH_MARKER → PRECISION_APPROACH
            → BIOMETRIC_VERIFY → DROP_PACKAGE → RETURN_HOME → LANDING → DISARM
```
Her durumda batarya / geofence / link / zaman aşımı denetlenir; ihlalde
**ABORT → RTL/LAND** (Safety First).

---

## Dizin yapısı

```
enesihayarisma/
├── README.md                  # bu dosya
├── requirements.txt
├── onboard/                     # Jetson Orin Nano görev yazılımı
│   ├── config.py              # TÜM parametreler (irtifa, PID, eşik, güvenlik)
│   ├── packet_protocol.py     # LoRa paket biçimi + CRC (ESP32 ile ortak)
│   ├── lora_receiver.py       # LoRa paket alımı/çözümü
│   ├── mavlink_interface.py   # Pixhawk/ArduCopter köprüsü (pymavlink)
│   ├── autonomous_takeoff.py  # pre-arm + arm + VTOL kalkış (Zeki)
│   ├── camera.py              # IMX219 / USB / test kamerası
│   ├── aruco_detector.py      # ArUco tespiti + poz kestirimi
│   ├── face_verifier.py       # biyometrik doğrulama (face_recognition)
│   ├── pid.py                 # anti-windup PID
│   ├── visual_servo.py        # hassas yaklaşma + sarmal arama
│   ├── package_dropper.py     # servo ile paket bırakma
│   ├── state_machine.py       # görev durumları/geçişleri
│   └── mission.py             # ANA orkestratör + failsafe izleyici
├── firmware/esp32_ground_station/            # ESP32 yer istasyonu (Attia)
│   ├── ground_station.ino
│   ├── packet_protocol.h
│   └── README.md
├── faces/                     # kayıtlı yüzler: alici_<id>.jpg
├── simulation/                      # simülasyon + testler
│   ├── software_demo.py       # kurulumsuz uçtan uca demo (video üretebilir)
│   ├── sim_backend.py         # FakeDrone fiziği + sentetik ArUco kamerası
│   ├── run_sitl.sh            # ArduPilot SITL başlatıcı
│   ├── test_mission_sitl.py   # görevi gerçek SITL'e karşı çalıştır
│   └── README.md
├── tools/
│   └── generate_aruco.py      # ped için yazdırılabilir marker üret
├── tests/                     # pytest birim + entegrasyon testleri
└── logs/                      # demo videosu / loglar
```

---

## Hızlı başlangıç

### 0) Bağımlılıklar
```bash
pip install -r requirements.txt
# Jetson'da OpenCV sistemde kuruluysa requirements'tan opencv satırını çıkar.
```

### 1) Kurulumsuz yazılım demosu (en hızlı doğrulama)
ArduPilot/Pixhawk/kamera gerekmez — tüm akışı gösterir:
```bash
cd sitl
KOKPIT_SIM=1 python3 software_demo.py               # başarılı teslimat
KOKPIT_SIM=1 python3 software_demo.py --reject       # biyometrik ret senaryosu
KOKPIT_SIM=1 python3 software_demo.py --save-video    # logs/demo.mp4 üret
```

### 2) Otomatik testler
```bash
KOKPIT_SIM=1 python3 -m pytest tests/ -q
```

### 3) Gerçek ArduPilot SITL (en gerçekçi yazılım testi)
```bash
cd sitl
./run_sitl.sh                              # Terminal 1
KOKPIT_SIM=1 python3 test_mission_sitl.py  # Terminal 2
```

### 4) Gerçek donanım (Jetson + Pixhawk)
```bash
# config.py: KOKPIT_SIM=0 ve mavlink_real / portlar doğru olmalı
cd drone
KOKPIT_SIM=0 python3 mission.py
```

---

## Konfigürasyon

Tüm ayarlar `onboard/config.py` içinde, gruplanmış dataclass'larda:
`LinkConfig` (bağlantılar), `CameraConfig`, `ArucoConfig`, `FlightConfig`
(irtifa/hız profili), `PIDConfig` (görsel servo kazançları + hız limitleri),
`FaceConfig` (eşik/oylama), `DropperConfig` (servo PWM), `SafetyConfig`
(batarya/geofence/zaman aşımı/sarmal arama).

`CFG.validate()` saha öncesi mantık tutarlılığını denetler (örn. paket bırakma
irtifasının 2–3 m hedefinde olması). `mission.setup()` bunu otomatik çağırır.

`KOKPIT_SIM` ortam değişkeni `1` → SITL/sim, `0` → gerçek donanım.

### Sahada ilk ayarlanacaklar
- `ArucoConfig.marker_length_m` — yazdırılan marker'ın **fiziksel** kenarı (m).
- Kamera kalibrasyonu — `camera_calibration.npz` (yoksa config varsayılanları).
- `DropperConfig.pwm_locked/pwm_released` — servonuza göre.
- `visual_servo.FWD_SIGN / RIGHT_SIGN` — kamera montaj yönüne göre işaretler.
- `PIDConfig` kazançları — konservatif başla, kademeli artır.

---

## Donanım (rapordan özet)
- **Uçuş kontrol:** Pixhawk 2.4.8 (ArduCopter), Holybro M9N GPS, Benewake TFS20 Lidar
- **Görev bilgisayarı:** NVIDIA Jetson Orin Nano (MAVLink ile Pixhawk'a bağlı)
- **Kamera:** WaveShare IMX219 (alt/marker + yüz)
- **Haberleşme:** LoRa E32 433 MHz (ped ↔ İHA)
- **Yer istasyonu:** ESP32 (TTGO T-Display) + NEO-M8N GPS + OV5640 + buton
- **Yük bırakma:** PWM servo mekanizması
- **Platform:** ZD550 karbon fiber quad, 6S 7000mAh, MTOW ≈ 3.5–4 kg

Pixhawk ↔ Jetson kablolaması ve ESP32 yer istasyonu kablolaması için
`firmware/esp32_ground_station/README.md` ve `onboard/config.py` yorumlarına bakın.

---

## ⚠️ Güvenlik kontrol listesi (drone düşmesin)

Bu yazılım, çok katmanlı güvenlik içerir: hız komutu kırpma, geofence, batarya/
link/uydu failsafe, zaman aşımları, biyometrik başarısızlıkta teslimatı askıya
alma, marker kaybında yerinde tutunma + sarmal arama. Yine de **gerçek uçuş
risklidir**. İlk uçuştan önce sırasıyla:

1. **Yazılım demosu** geçti mi? (`software_demo.py`)
2. **Tüm testler** geçti mi? (`pytest tests/`)
3. **SITL** görevi tamamlıyor mu? (`run_sitl.sh` + `test_mission_sitl.py`)
4. **Pervanesiz** masa testi: arm/servo/telemetri doğru mu?
5. **Bağlı (tethered)** veya **AltHold/Loiter** elle uçuş: titreşim/EKF sağlığı.
6. ArduPilot **failsafe** parametreleri ayrı yapılandırılmış mı? (BATT_*, FS_*,
   FENCE_*) — bu yazılımın failsafe'i bunların **yerine geçmez, tamamlar**.
7. İlk otonom denemeyi **geniş, boş, izinli** bir sahada, **kill-switch hazır**
   bir pilot gözetiminde yap.
8. Düşük irtifa/hız limitleriyle başla (`config.py`), kademeli artır.

> Otonom paket bırakma irtifası varsayılan **2.5 m** (config `drop_altitude_m`),
> rapordaki 2–3 m şartıyla uyumludur ve `validate()` ile denetlenir.

---

## Test durumu

`pytest tests/ -q` → **26 passed**

- Paket protokolü: CRC vektörü, roundtrip, gürültülü akış, bozuk CRC reddi
- C (ESP32) ↔ Python (Jetson) paket baytları **birebir aynı** (doğrulandı)
- PID: yakınsama (<15 cm), kararlılık (salınımsız), çıkış limiti, anti-windup
- ArUco: merkezli/kaymış marker tespiti, işaret yönleri, poz
- Config: doğrulama kuralları
- **Uçtan uca görev (entegrasyon):** başarılı teslimat + biyometrik ret senaryosu
  (gerçek ArUco + gerçek PID, FakeDrone fiziğiyle kapalı döngü)
