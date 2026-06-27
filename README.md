# Kokpit UAV

**Teknofest 2026 — Uluslararası İHA Yarışması, Serbest Görev Kategorisi**
Ankara Yıldırım Beyazıt Üniversitesi · Kokpit Takımı

---

## Proje Nedir?

Otonom hassas teslimat yapan bir dronedur. Görev tam otonom çalışır, insan müdahalesi gerekmez:

1. Yer istasyonunda (ped) bir kullanıcı **butona basar**. Pedin üzerindeki ESP32 mikrodenetleyici, GPS modülünden anlık konumu ve kamerasından alıcının yüzünü yakalar.
2. Bu veri **AES-128 şifreli LoRa paketinde** drone'a iletilir (433 MHz).
3. Drone (Pixhawk + ArduCopter) komutu alır, **dikey kalkış yapar**, hedef koordinatlara yönelir.
4. Hedef üzerinde **ArUco marker** ile santimetre hassasiyetinde pede yaklaşır.
5. Üzerindeki kamera ile **alıcının yüzünü tanır** (TensorRT hızlandırmalı CNN). Eşleşme %90 üzerindeyse devam, altındaysa teslimatı iptal eder.
6. Servo motorla **paket bırakılır**.
7. Drone otonom olarak **üsse döner (RTL)** ve iner.

Proje raporu (jüri'ye sunulan resmi belge) → [`docs/report/884462.pdf`](docs/report/884462.pdf)

---

## Hızlı Başlangıç

Gerçek donanıma ihtiyaç yok — tüm pipeline simülasyonda çalışır:

```bash
git clone https://github.com/Mohamedattiadev/kokpit-uav
cd kokpit-uav
make install        # Python bağımlılıkları
make test           # 26 unit test, hepsi geçmeli
make demo           # donanımsız tam görev simülasyonu (terminal'de izlenir)
make sitl           # ArduCopter SITL ile gerçek uçuş simülasyonu
```

Gerçek donanım için (Jetson kurulumu, ArduPilot parametreleri, kablolama, kalibrasyon, saha operasyonu, sorun giderme):
→ [`docs/KILAVUZ.md`](docs/KILAVUZ.md)

---

## Nereye Bakmalıyım?

| Belge | İçerik |
|---|---|
| [`docs/KILAVUZ.md`](docs/KILAVUZ.md) | Adım adım kurulum + saha kullanım kılavuzu. Yeni başlayan buradan başlamalı. |
| [`docs/PLAN.md`](docs/PLAN.md) | Yapılacaklar listesi. 4 sprint, görev atamaları, effort tahminleri. |
| [`docs/QUESTIONS_FOR_TEAM.md`](docs/QUESTIONS_FOR_TEAM.md) | Takım kararı bekleyen / verilen sorular ve gerekçeleri. |
| [`docs/report/`](docs/report/) | Resmi yarışma raporu (PDF) ve donanım alım listesi. **Canonical spec — yazılım bundan sapamaz.** |
| [`docs/prompts/`](docs/prompts/) | Modül bazlı teknik prompt'lar (AI destekli geliştirme için). |

---

## Repo Yapısı

```
kokpit-uav/
├── onboard/                          Jetson görev bilgisayarı (Python)
│                                     Drone üzerinde çalışan ana yazılım:
│                                     görev mantığı, ArUco, yüz tanıma,
│                                     MAVLink, LoRa alıcı, servo kontrol.
│
├── firmware/esp32_ground_station/    Yer istasyonu (Arduino/ESP32)
│                                     Buton + GPS + kamera + LoRa gönderici.
│
├── simulation/                       ArduCopter SITL + sahte donanım
│                                     Donanımsız full akış testi.
│
├── ardupilot/                        Pixhawk parametre dosyaları
│                                     MissionPlanner üzerinden yüklenir.
│
├── tests/                            pytest unit testler
├── tools/                            Kalibrasyon scriptleri
├── data/faces/                       Alıcı yüz veritabanı (gitignored)
├── docs/                             KILAVUZ + PLAN + rapor + spec
└── .github/workflows/                CI (lint + test + smoke)
```

---

## Takım ve Sorumluluklar

| Üye | Sorumluluk | Ana Dosyalar |
|---|---|---|
| **Arda** | Görev durum makinesi, görsel servo, ArUco tespiti, yüz tanıma, paket bırakma | `onboard/mission.py`, `visual_servo.py`, `aruco_detector.py`, `face_verifier.py`, `package_dropper.py` |
| **Zeki Emir** | Otonom kalkış, pre-arm kontroller, MAVLink köprüsü | `onboard/autonomous_takeoff.py`, `mavlink_interface.py` |
| **Attia** | Yer istasyonu firmware, LoRa paket protokolü (her iki uç) | `firmware/esp32_ground_station/`, `onboard/packet_protocol.py` |
| **Enes Eryiğit** | Takım sorumlusu, raporlama, sistem mimarisi | (proje yönetimi) |

---

## Mevcut Durum

- Yazılım simülasyonda uçtan uca çalışır. 26 unit test geçer (`make test`).
- 12 kritik bug ve eksik tespit edildi — `docs/PLAN.md` Sprint 0-4 ile sırayla kapatılıyor. Yaklaşık effort: 13 gün.
- Gerçek uçuş henüz yapılmadı. Saha tuning ve test uçuşları sprint 4'te.

Yarışmaya hazırlanmak için `docs/PLAN.md` baştan sona uygulanmalı. Bu repo'da geliştirme yapan herkes önce o dosyayı okumalı.

---

## Güvenlik Notları

**Pilot her zaman önceliklidir.** Radyo kumandası Manual moduna alındığında otonom kontrol kendiliğinden devre dışı kalır; drone read-only moduna geçer.

Failsafe katmanları (otomatik RTL veya LAND tetikler):
- Batarya voltaj eşiği (6S için 22.0 V düşük, 21.0 V kritik)
- GPS fix kaybı (5 sn üzeri)
- MAVLink heartbeat kaybı (3 sn üzeri)
- Geofence ihlali (yarışma alanı polygonu dışı)
- RC link kaybı
- Crash tespiti (roll/pitch 45 derece üzeri → acil disarm)

İlk gerçek uçuş öncesi zorunlu adımlar `docs/KILAVUZ.md` içinde listelidir: kompas/radyo/ESC kalibrasyonu, geofence yüklemesi, batarya failsafe parametre kontrolü, manual → stabilize → loiter → guided kademe testleri.

---

## Lisans

Bu proje [MIT lisansı](LICENSE) altında dağıtılmaktadır.

---

İletişim ve katkı için takım kanalı (WhatsApp / Discord). Issue ve pull request'ler doğrudan bu repo üzerinden kabul edilir.
