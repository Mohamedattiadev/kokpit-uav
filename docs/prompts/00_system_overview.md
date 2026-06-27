# 00 — SİSTEM GENEL BAKIŞ (Master Context)

> **HER MODÜL PROMPTU BU DOSYAYI ÖNCE OKUMALI.** Bu dosya, Kokpit takımının Teknofest İHA Yarışması Serbest Görev kategorisi için geliştirdiği "Otonom Hassas Teslimat ve Biyometrik Doğrulamalı Lojistik Sistemi" projesinin yazılım mimarisini tanımlar. Her ayrı yazılım modülü kendi prompt dosyasıyla bağımsız bir Claude Code oturumunda geliştirilir, ancak hepsi aynı monorepo'da bu dokümandaki sözleşmelere göre konuşur.

---

## 1. Görev Özeti

1. Yer istasyonu (Ped) üzerindeki buton bastırılır.
2. ESP32, NEO-M8N GPS'ten koordinat ve OV5640 kameradan yüz görüntüsü yakalar.
3. Veri AES şifreli + CRC'li bir LoRa paketinde İHA'ya gönderilir.
4. Jetson Orin Nano paketi çözer, GPS'i Pixhawk'a MAVLink waypoint olarak verir, yüzü TensorRT modeline kıyaslar.
5. Pixhawk (ArduCopter) otonom VTOL kalkış + waypoint takibi yapar.
6. Hedefte Jetson, IMX219 kamera ile ArUco marker'ı tespit eder, visual servoing PID döngüsüyle ped merkezine ±5 cm hassasiyetle yaklaşır (Lidar TFS20 ile irtifa doğrulanır).
7. Kameradan canlı alıcının yüzü tanınır (≥%90 eşleşme), PWM servo tetiklenir, paket bırakılır.
8. RTL, üsse iniş, DISARM.

## 2. Donanım Envanteri (referans için sabit)

| Konum | Bileşen | Notlar |
|---|---|---|
| Yer İstasyonu | ESP32 (TTGO T-Display) | Çift çekirdek, OLED ekran |
| Yer İstasyonu | NEO-M8N GPS | UART, NMEA |
| Yer İstasyonu | OV5640 kamera | Yetkili yüz capture |
| Yer İstasyonu | LoRa E32 433T20D | UART, RF link |
| Yer İstasyonu | Buton + LED | Fiziksel tetikleme |
| İHA | Pixhawk 2.4.8 | ArduCopter |
| İHA | Jetson Orin Nano Super | Mission computer |
| İHA | LoRa E32 433T20D | RX |
| İHA | Holybro M9N GPS | Pixhawk'a bağlı |
| İHA | Benewake TFS20 Lidar | UART, irtifa |
| İHA | WaveShare IMX219-160 | CSI, ArUco + yüz |
| İHA | Servo (PWM) | Paket bırakma |
| GCS | SIK Telemetry V3 | Pixhawk telemetri |

## 3. Monorepo Yapısı (TAVSİYE — uygulanacak)

```
kokpit-iha/
├── firmware/
│   └── esp32_ground/         # PlatformIO / Arduino — yer istasyonu
├── jetson/
│   └── mission_computer/     # Python 3.10, görev bilgisayarı
│       ├── src/kokpit/
│       │   ├── lora_rx.py
│       │   ├── mavlink_bridge.py
│       │   ├── aruco_servoing.py
│       │   ├── face_recognition/
│       │   ├── sensor_fusion.py
│       │   ├── state_machine.py
│       │   └── main.py
│       └── tests/
├── shared/
│   └── protocol/             # LoRa paket sözleşmesi (TEK doğru kaynak)
│       ├── packet_spec.md
│       ├── packet.h          # C — ESP32 tarafı include
│       └── packet.py         # Python — Jetson tarafı import
├── sim/
│   └── simulation/                 # ArduCopter SITL + Gazebo dünyası
├── gcs/                      # SIK telemetri izleme arayüzü
├── tests/                    # Entegrasyon testleri
├── docs/
└── README.md
```

## 4. Modüller Arası Sözleşme

**LoRa paketi tek doğru kaynak: `shared/protocol/packet_spec.md`.**
ESP32 ve Jetson modülleri bu spec'ten türetilen `packet.h` / `packet.py` dosyalarını kullanır. Sözleşme değişirse spec güncellenir, iki taraf yeniden derlenir/test edilir.

**MAVLink mesaj tipleri** (Jetson↔Pixhawk):
- `SET_MODE` (GUIDED, AUTO, RTL, LAND)
- `COMMAND_LONG` (`MAV_CMD_NAV_TAKEOFF`, `MAV_CMD_DO_SET_SERVO`)
- `SET_POSITION_TARGET_LOCAL_NED` (visual servoing için)
- `MISSION_ITEM_INT` (waypoint yükleme)
- `HEARTBEAT`, `BATTERY_STATUS`, `GPS_RAW_INT`, `RANGEFINDER`

**Süreç içi IPC (Jetson içinde):**
- Tek `asyncio` event loop + paylaşılan `MissionState` dataclass
- Modüller arası iletişim `asyncio.Queue` ve Pub/Sub pattern

## 5. Çoklu Ajan Çalışma Modeli (TAVSİYE)

Her modül prompt'u **ayrı Claude Code oturumunda** paralel çalıştırılabilir:
1. Geliştirici uygun klasöre `cd` eder.
2. İlgili `NN_*.md` prompt'unu yapıştırır.
3. Claude önce `00_system_overview.md` + `shared/protocol/packet_spec.md` okur.
4. Claude executor'a netleştirici sorular sorar (dil, framework varyantı, vb.) — *bu sorular her prompt'un başında zorunlu*.
5. Sözleşmeye uygun kod üretir, kendi `tests/` klasörüne unit test yazar.
6. Sözleşmeyi değiştirmesi gerekirse **önce `shared/protocol/` PR'ı** açar, diğer modüller bilgilendirilir.

## 6. Güvenlik (TAVSİYE)

- LoRa paketi: **AES-128-CCM** (16-byte key) + 4-byte monoton sequence number (replay guard) + CRC-16/CCITT
- Anahtar: `shared/protocol/keys/` altında `.gitignore`'lu, repo'ya commit edilmez; her takım üyesi local'inde
- Yüz veri seti: `jetson/mission_computer/data/faces/` — `.gitignore`'lu
- Failsafe: tüm modüller `MissionState.abort_reason` set ederek RTL tetikleyebilir

## 7. Test Stratejisi (TAVSİYE)

İki katman:
1. **SITL+Gazebo**: ArduCopter SITL + Gazebo + sahte LoRa (UDP loopback) + sahte kamera (video dosyası). Tüm görev döngüsü CI'da koşturulabilir.
2. **HIL (Hardware-In-The-Loop)**: Gerçek ESP32 ↔ gerçek Jetson, Pixhawk SITL. Sonra tam donanım.

## 8. Performans Hedefleri (raporda taahhüt edilen)

- Navigasyon sapma: ≤ ±0.8 m
- İniş radyal hata: ≤ 14 cm (hedef ±5 cm)
- Yüz tanıma doğruluk: ≥ %90 (farklı ışıkta)
- Görev bilgisayarı end-to-end gecikme: ≤ 200 ms (LoRa RX → MAVLink TX)
- LoRa paket kaybı toleransı: 3 ardışık kayıpta failsafe

## 9. Geliştirme Sırası (önerilen)

```
shared/protocol  →  esp32_ground + lora_rx (paralel)
                 →  mavlink_bridge
                 →  aruco_servoing + face_recognition + sensor_fusion (paralel)
                 →  servo_release
                 →  state_machine (tüm modülleri orchestrate eder)
                 →  gcs_telemetry
                 →  sitl entegrasyon testi
```

## 10. Her Prompt'un Davranış Kuralı

Her modül prompt'u Claude'a şu sırayı dayatır:
1. Bu dosyayı (`00_system_overview.md`) ve `shared/protocol/packet_spec.md` (varsa) oku.
2. Executor'a prompt'un başındaki **netleştirme sorularını** sor, cevap bekle.
3. Eksik klasörleri scaffold et.
4. Kod yaz, type hint + docstring + kısa yorum (sadece "neden").
5. `pytest` veya platform testleri yaz, koş.
6. README/kullanım notu güncelle.
7. Sözleşme değişikliği gerekiyorsa `shared/protocol/` önce.

---

**Bu dosya canlı.** Mimari değişirse buraya işle, modül prompt'ları otomatik senkron olur.
