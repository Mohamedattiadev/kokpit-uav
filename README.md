# Kokpit UAV

[![CI](https://github.com/Mohamedattiadev/kokpit-uav/actions/workflows/ci.yml/badge.svg)](https://github.com/Mohamedattiadev/kokpit-uav/actions/workflows/ci.yml)
![tests](https://img.shields.io/badge/tests-369%20passed-brightgreen)
![status](https://img.shields.io/badge/yaz%C4%B1l%C4%B1m-tamam-brightgreen)
![donanim](https://img.shields.io/badge/donan%C4%B1m-2%2F4%20kod%20haz%C4%B1r-yellow)

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

## Demo Videoları

Simülasyon üzerinde kaydedilmiş uçtan uca görev videoları (`logs/`) —
GitHub üzerinde dosyaya tıklayıp doğrudan izleyebilirsin:

| Video | Senaryo |
|---|---|
| [`logs/gazebo_flight_3d.mp4`](logs/gazebo_flight_3d.mp4) | Gazebo'da gerçek 3D fizik simülasyonu: kalkış → hedefe gidiş → hassas yaklaşma → biyometrik doğrulama → paket bırakma → RTL → iniş. |
| [`logs/demo.mp4`](logs/demo.mp4) | Standart yazılım demo'su (`make demo`) — tam otonom görev, donanımsız. |
| [`logs/demo_reject.mp4`](logs/demo_reject.mp4) | Biyometrik doğrulama **başarısız** senaryosu — yanlış kişi tespit edilince teslimat iptal ediliyor. |
| [`logs/demo_wind5ms.mp4`](logs/demo_wind5ms.mp4) | Saha rüzgar limiti olan 5 m/s rüzgar altında yaklaşma testi. |
| [`logs/dashboard_replay_sitl.mp4`](logs/dashboard_replay_sitl.mp4) | SITL uçuşu sonrası web replay dashboard'unda (timeline + harita + grafik) görev tekrar oynatması. |

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
| [`docs/DONANIM_DURUM.md`](docs/DONANIM_DURUM.md) | **Kısa özet: şu an tam olarak ne kaldı, kim yapacak.** Detaya girmeden hızlı bakış için. |
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

- 369 unit test geçer + 1 skip (`make test`, ~12 dk — gerçek dünya arıza enjeksiyon sweep'leri eklendi). CI yeşil (GitHub Actions).
- İŞ-1 (TensorRT yüz tanıma engine build) ve İŞ-3'ün (ESP32 RX parser) **kod tarafı tamamlandı**, gerçek Jetson Orin Nano'da doğrulandı, `main`'e alındı. Detay ve kalan fiziksel adımlar → [`docs/DONANIM_PLANI.md`](docs/DONANIM_PLANI.md).
- Gerçek-dünya arıza enjeksiyonu (rüzgar/ArUco geometri/attitude/biyometrik/sensör bozulması/çoklu-arıza) simülasyon katmanına eklendi — saha testi öncesi risk azaltma, donanımın yerini TUTMAZ.
- Sprint 0 + Sprint 1 + Sprint 2 + Sprint 3 + M1-M12 + N1-N12 + dashboard pro tamam.
- Simülasyonda uçtan uca otonom görev çalışır.
- Rapor (`docs/report/884462.pdf`) uyumu: Q1-Q7 kararlar korundu, ihlal yok.

### N1-N12 (FINISH_SOFTWARE_PROMPT_V2 final iterasyon)

| # | Madde | Commit | Test |
|---|---|---|---|
| N1 | preflight_check.py — arm öncesi 12 kontrol | `6096675` | 14 |
| N2 | Gazebo SITL + 6 senaryo (SDF + skript) | `8e3d0e4` | 8 |
| N3 | replay dashboard (Flask timeline + plot) | `b7020d0` | 5 |
| N4 | telemetry recorder (forensic CSV 1 Hz) | `ac74024` | 4 |
| N5 | sysid çakışma koruma + scan_sysid | `d13dac7` | 4 |
| N6 | hava durumu pre-check (Open-Meteo) | `d810d4c` | 6 |
| N7 | AutoTune headless orchestrator | `c42ed01` | 4 |
| N8 | live MJPEG stream + ArUco overlay | `9da43e9` | 5 |
| N9 | ESP32 hot swap BOOT_BEACON station_id | `c44d3f7` | 4 |
| N10 | SAHA_KART.md + make print-card | `c852b1d` | — |
| N11 | runs/ index + aylık tar.gz archive | `ba8af10` | 3 |
| N12 | final integration smoke (uçtan uca) | `ccd91a1` | 5 |
| — | hardening: param hash + dash auth + CI | `62bf041` | — |
| — | saha otomasyonu: dash_pw + weather + Make | `b4dfa73` | — |

### Dashboard / observability genişletme (15 madde)

| Madde | Commit | Test |
|---|---|---|
| #9+#10 mission event emitter + run dir lifecycle | `1b266ed` | 5 |
| #12 /health endpoint + bileşen registry | `e0b7576` | 4 |
| #1+#3+#5 Leaflet map + phase timeline bar + failsafe panel | `a13b604` | 5 |
| #2+#4 live tail poll + search/filter chips | `b6731e2` | 3 |
| #6+#7+#8 compare view + download zip + all-time stats | `9ec4c9c` | 7 |
| #11+#14+#15 live MJPEG iframe + .tlog export + PDF/MD report | `310a272` | 5 |
| #13 webhook alerter (Slack/Discord/Telegram uyumlu) | `001044e` | 4 |

Toplam: 33 ek test (270 → 303), 7 yeni commit, ~1500 LOC dashboard + event sistemi.

### Önceki iterasyonlar: 14 commit, 62 yeni test (146 → 208 → 270), 18 yeni dosya, ~2500 LOC.

### M1-M12 (önceki iterasyon)

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

1. ~~**TensorRT engine build.**~~ **Kod tarafı TAMAM** ([PR #1](https://github.com/Mohamedattiadev/kokpit-uav/pull/1)) — `tools/build_face_trt.py` TensorRT 10.x'e uyumlu hale getirildi, Jetson Orin Nano'da det/emb engine'leri gerçekten derlendi, `tests/test_face_trt.py` 6/6 PASS. **Kalan (fiziksel/sudo):** `sudo nvpmodel -m 0` + systemd servis kurulumu — bkz. checklist.
2. **Extrinsics kalibrasyon.** Kamera + lidar gövdeye monte edildikten sonra cetvelle ölçü alınıp `tools/calibrate_extrinsics.py` ile kaydedilmeli. Yapılmazsa iniş 5-10 cm kayar. *(henüz başlanmadı — donanım montajı gerekiyor)*
3. ~~**ESP32 RX parser.**~~ **Kod tarafı TAMAM** ([PR #1](https://github.com/Mohamedattiadev/kokpit-uav/pull/1)) — `packet_protocol.h` + `ground_station.ino`'ya TELEMETRY parser, TFT gösterimi, buzzer uyarısı ve çift-tık MANUAL_REQUEST eklendi; host-derlenmiş harness ile 7/7 PASS doğrulandı. **Kalan (fiziksel):** gerçek ESP32 kartına yükleme + saha LoRa testi.
4. **Saha test uçuşları.** ArduCopter PID tune + manuel → stabilize → loiter → guided kademe testleri. *(henüz başlanmadı — 1-3 tamamlanmadan anlamlı değil)*

### N1-N12 sahada yapılacak (yazılım hazır, donanım/insan gerekir)

- Gerçek `tools/preflight_check.py` Pixhawk+Jetson takılı haldeyken 12/12 PASS.
- `gz sim` kurulu Jetson'da `bash simulation/gazebo/run_scenarios.sh` 6 senaryo gerçek fizik.
- AutoTune ilk uçuş: `python3 tools/autotune.py` orchestrator + pilot RC AUTOTUNE switch.
- `sudo bash scripts/gen_dash_pw.sh` (Jetson'da, /etc/kokpit/dash_pw secret üretir).
- `/etc/kokpit/site` dosyasına `KOKPIT_LAT=` ve `KOKPIT_LON=` saha koordinatları.
- `sudo systemctl enable --now kokpit-weather.timer kokpit-runs-archive.timer`.
- `docs/SAHA_KART.md` telefon alanları doldur, `make print-card` ile A4 yazdır.
- Param tune sonrası `make refresh-param-hash` ile preflight hash güncelle.

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
