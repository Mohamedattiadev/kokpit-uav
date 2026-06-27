# Kokpit UAV

**Teknofest 2026 · İHA Yarışması · Serbest Görev** — Ankara Yıldırım Beyazıt Üniversitesi

Otonom drone. Buton bas → hedefe uç → yüzü tanı → paketi bırak → üsse dön.

---

## Ne Yapar?

1. **Yer istasyonunda** buton basılır (ESP32 + GPS + kamera)
2. **LoRa** ile drone'a GPS koordinatı + alıcı kimliği gider
3. **Drone otonom kalkar** (Pixhawk + ArduCopter)
4. Hedefe gider, **ArUco marker** ile cm hassasiyetinde yaklaşır
5. **Yüz tanıma** ile alıcıyı doğrular
6. Eşleşirse **servo açılır**, paket bırakılır
7. **RTL** ile üsse döner ve iner

---

## Hızlı Başlangıç

```bash
git clone https://github.com/Mohamedattiadev/kokpit-uav
cd kokpit-uav
make install        # bağımlılıkları kur
make test           # 26 unit test
make demo           # donanımsız tam akış simülasyonu
make sitl           # ArduCopter SITL ile gerçek uçuş simülasyonu
```

Gerçek donanım kurulumu → [`docs/KILAVUZ.md`](docs/KILAVUZ.md)

---

## Önemli Dosyalar

| Nereye Bakacaksın | Ne İçin |
|---|---|
| [`docs/KILAVUZ.md`](docs/KILAVUZ.md) | **Kurulum, kablolama, kalibrasyon, saha operasyonu, sorun giderme** — başla buradan |
| [`docs/PLAN.md`](docs/PLAN.md) | Yapılacaklar listesi (bug fix → güvenlik → rapor uyumu → saha) |
| [`docs/QUESTIONS_FOR_TEAM.md`](docs/QUESTIONS_FOR_TEAM.md) | Takım kararı bekleyen 12 soru |
| [`docs/report/`](docs/report/) | Resmi yarışma raporu (PDF) — **canonical spec** |
| [`docs/prompts/`](docs/prompts/) | Modül modül teknik spec (AI ile geliştirme için) |

---

## Repo Yapısı

```
kokpit-uav/
├── onboard/              Jetson görev bilgisayarı (Python) — drone beyni
├── firmware/             ESP32 yer istasyonu (Arduino) — buton + GPS + LoRa
├── simulation/           SITL + sahte donanım — gerçek uçuş öncesi test
├── tests/                pytest unit testler
├── tools/                Kalibrasyon scriptleri (kamera, ArUco)
├── ardupilot/            Pixhawk param dosyaları
├── data/faces/           Alıcı yüz veritabanı (gitignored)
└── docs/                 KILAVUZ + PLAN + raporlar + spec
```

---

## Takım

| Kim | Ne Yapar | Kod |
|---|---|---|
| **Arda** | Görev mantığı, ArUco, yüz tanıma, servo | `onboard/mission.py`, `visual_servo.py`, `aruco_detector.py`, `face_verifier.py`, `package_dropper.py` |
| **Zeki Emir** | Otonom kalkış, MAVLink | `onboard/autonomous_takeoff.py`, `mavlink_interface.py` |
| **Attia** | Yer istasyonu, LoRa paket protokolü | `firmware/esp32_ground_station/`, `onboard/packet_protocol.py` |
| **Enes** | Takım sorumlusu, raporlama | — |

---

## Mevcut Durum

- ✅ Yazılım simülasyonda uçtan uca çalışır (26/26 test geçer)
- ⚠️ **12 kritik bug/eksik var** — [`docs/PLAN.md`](docs/PLAN.md) Sprint 0–4 ile kapatılacak (~13 gün effort)
- ❌ Gerçek uçuş yapılmadı — saha tuning + test uçuşları gerekli

**Yarışmaya hazır olmak için → `docs/PLAN.md` baştan sona uygula.**

---

## Güvenlik

🚨 **Pilot her zaman önceliklidir.** Radyo kumanda Manual moduna alındığında otonomi durur.

Failsafe katmanları: batarya / GPS / link / geofence / RC kayıp → otomatik **RTL**. Detay: [`docs/KILAVUZ.md`](docs/KILAVUZ.md).

İlk gerçek uçuş öncesi zorunlu: kompas + radyo + ESC kalibrasyonu, geofence yüklü, batarya failsafe param'ları kontrol edildi, manual + stabilize + loiter kademe testleri tamamlandı.

---

Lisans: [MIT](LICENSE)
