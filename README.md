# Kokpit UAV

[![CI](https://github.com/Mohamedattiadev/kokpit-uav/actions/workflows/ci.yml/badge.svg)](https://github.com/Mohamedattiadev/kokpit-uav/actions/workflows/ci.yml)
![tests](https://img.shields.io/badge/tests-203%20passed-brightgreen)
![status](https://img.shields.io/badge/yaz%C4%B1l%C4%B1m-tamam-brightgreen)
![donanim](https://img.shields.io/badge/donan%C4%B1m-bekleniyor-yellow)

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
make test           # 203 unit test, hepsi geçmeli (~2 dk)
make demo           # donanımsız tam görev simülasyonu (terminal'de izlenir)
make sitl           # ArduCopter SITL ile gerçek uçuş simülasyonu
```

Gerçek donanım için (Jetson kurulumu, ArduPilot parametreleri, kablolama, kalibrasyon, saha operasyonu, sorun giderme):
→ [`docs/KILAVUZ.md`](docs/KILAVUZ.md)

---

## Nereye Bakmalıyım?

| Belge | İçerik |
|---|---|
| [`docs/DONANIM_PLANI.md`](docs/DONANIM_PLANI.md) | **🔧 Donanım ekibi buradan başlamalı.** 4 iş için adım adım rehber + komut + sorun giderme. |
| [`docs/KILAVUZ.md`](docs/KILAVUZ.md) | Adım adım kurulum + saha kullanım kılavuzu. |
| [`docs/PLAN.md`](docs/PLAN.md) | Yapılacaklar listesi. 4 sprint, görev atamaları, effort tahminleri. M1–M12 tamam. |
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
├── tests/                            pytest unit testler (203 test)
├── tools/                            Kalibrasyon + TRT engine build
├── scripts/                          Görev sonrası analiz (plot)
├── systemd/                          Jetson auto-restart servisi
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

**Yazılım tarafı tamamlandı.**

- 203 unit test geçer (`make test`, ~2 dk). CI yeşil (GitHub Actions).
- Sprint 0 + Sprint 1 (uçuş güvenliği) + Sprint 2 (rapor uyumu) + Sprint 3 (operasyon kalitesi) tamam.
- Simülasyonda uçtan uca otonom görev çalışır.

Tamamlanan 12 ana modül:

| # | Modül | Açıklama |
|---|---|---|
| M1 | TensorRT yüz tanıma | RetinaFace + ArcFace, dlib fallback |
| M2 | Extrinsics dönüşümü | Kamera/lidar mount offset → gövde çerçevesi |
| M3 | Zaman senkronu | MAVLink SYSTEM_TIME + ESP32 GPS UTC |
| M4 | Watchdog + systemd | Jetson çökerse 15 sn'de otomatik restart |
| M5 | Log indirme | Pixhawk dataflash + plot aracı |
| M6 | Yaw hizalama | Teslimatta drone alıcıya bakar |
| M7 | LoRa link telemetri | RSSI + paket kaybı + telemetry paket |
| M8 | Reboot kurtarma | Mid-mission reboot → READ_ONLY mod |
| M9 | Pilot override | Manuel moda alınca Jetson çekilir |
| M10 | BOOT_BEACON | ESP32 reboot sonrası replay reset |
| M11 | CI doğrulama | requirements-ci.txt, 3 dk pipeline |
| M12 | Arşimet sarmal | Sürekli velocity arama trajektorisi |

**Donanım bekleyen 4 iş** (detaylı adım adım plan → [`docs/DONANIM_PLANI.md`](docs/DONANIM_PLANI.md)):

1. **TensorRT engine build.** Jetson Orin Nano + JetPack 6.x kurulduğunda `tools/build_face_trt.py` çalıştırılacak. Bu yapılmazsa yüz tanıma CPU üzerinde 1-2 FPS'te kalır (dlib fallback).
2. **Extrinsics kalibrasyon.** Kamera + lidar gövdeye monte edildikten sonra cetvelle ölçü alınıp `tools/calibrate_extrinsics.py` ile kaydedilmeli. Yapılmazsa iniş 5-10 cm kayar.
3. **ESP32 RX parser.** Drone'dan gelen TELEMETRY paketini yer istasyonu TFT'sinde göstermek için firmware'e parser eklenecek. Saha öncesi ikinci bir firmware PR'ı.
4. **Saha test uçuşları.** ArduCopter PID tune + manuel → stabilize → loiter → guided kademe testleri.

Donanım ekibi için tam detaylı plan (malzeme listesi, komutlar, doğrulama checklist'i, sorun giderme): [`docs/DONANIM_PLANI.md`](docs/DONANIM_PLANI.md).

---

## Güvenlik Notları

**Pilot her zaman önceliklidir.** Manuel kontrol iki yolla alınabilir:

1. **RC kumanda mode switch** (birincil yol, anlık). Pilot RC üzerinden MANUAL / STABILIZE / ACRO moduna geçtiğinde Jetson otomatik tanır, komut göndermeyi keser. ArduCopter zaten pilot stick'lerini birinci kabul eder.
2. **LoRa MANUAL_REQUEST paketi** (yedek, RC link zayıfsa). Yer istasyonundaki butonla `LOITER` veya istenen moda alma talebi gönderilir. Drone `set_mode(LOITER)` yapar + Jetson komut göndermeyi keser; pilot sonra RC ile istediği moda alır.

Failsafe katmanları (otomatik RTL veya LAND tetikler):
- Batarya voltaj eşiği (6S için 22.0 V düşük, 21.0 V kritik)
- GPS fix kaybı (5 sn üzeri)
- MAVLink heartbeat kaybı (3 sn üzeri)
- Geofence ihlali (yarışma alanı polygonu dışı)
- RC link kaybı
- Crash tespiti (roll/pitch 45 derece üzeri → acil disarm)

İlk gerçek uçuş öncesi zorunlu adımlar `docs/KILAVUZ.md` içinde listelidir: kompas/radyo/ESC kalibrasyonu, geofence yüklemesi, batarya failsafe parametre kontrolü, manual → stabilize → loiter → guided kademe testleri.

---

## systemd (Jetson Auto-Restart)

Jetson çöktüğünde otomatik restart için sdnotify tabanlı watchdog:

```bash
pip install sdnotify
sudo cp systemd/kokpit-mc.service /etc/systemd/system/
sudo systemctl enable kokpit-mc
sudo systemctl start kokpit-mc
journalctl -u kokpit-mc -f
```

Ana döngü her 5 sn `WATCHDOG=1`; 15 sn yanıt yoksa systemd servisi restart eder.

---

## Lisans

Bu proje [MIT lisansı](LICENSE) altında dağıtılmaktadır.

---

İletişim ve katkı için takım kanalı (WhatsApp / Discord). Issue ve pull request'ler doğrudan bu repo üzerinden kabul edilir.
