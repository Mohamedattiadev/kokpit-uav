# 01 — ESP32 YER İSTASYONU (Ground Station / Ped)

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `shared/protocol/packet_spec.md` (yoksa: önce `02_lora_protocol.md` çalıştırılmalı — executor'a bildir ve dur)

## Görev
ESP32 (TTGO T-Display) üzerinde yer istasyonu firmware'i geliştir. Buton tetiklemesiyle GPS+yüz görüntüsünü yakalar, LoRa paketinde İHA'ya gönderir, OLED ekrana durum yazar.

## Donanım Bağlantıları (sabit referans)
- **NEO-M8N GPS** → UART1 (RX=GPIO16, TX=GPIO17), 9600 baud, NMEA
- **OV5640 Kamera** → SCCB I²C (SDA=GPIO21, SCL=GPIO22) + 8-bit paralel data (D0–D7 → GPIO34..GPIO39 vb. ESP32-CAM modülü kullanılıyorsa standart pinout)
- **LoRa E32 433T20D** → UART2 (RX=GPIO27, TX=GPIO26), M0=GPIO32, M1=GPIO33, AUX=GPIO25, 9600 baud config
- **Buton** → GPIO0 (pull-up, FALLING edge interrupt)
- **Durum LED** → GPIO2
- **TTGO T-Display ST7789 OLED** → SPI (TFT_MOSI=GPIO19, TFT_SCLK=GPIO18, TFT_CS=GPIO5, TFT_DC=GPIO16, TFT_RST=GPIO23, TFT_BL=GPIO4)

> Pinout çakışması varsa executor'a bildir, executor karar versin.

## Açılışta Executor'a Sor (zorunlu)
Aşağıdaki soruları executor'a tek tek sor, cevap bekle, sonra kod yaz:

1. **Framework**: PlatformIO + Arduino mı, PlatformIO + ESP-IDF mi, Arduino IDE mi? *(Tavsiye: PlatformIO + Arduino — daha hızlı iterasyon)*
2. **Kamera modülü**: Gerçek OV5640 kütüphanesi mi (`esp32-camera`), yoksa ESP32-CAM (OV2640) substitute mu? *(Rapor OV5640 diyor; ESP32 tarafında OV5640 kütüphanesi sınırlı — executor onaylasın)*
3. **TTGO T-Display panel**: Standart 240×135 ST7789 mi, başka bir varyant mı?
4. **Pinout**: Yukarıdaki tavsiye pinout OK mi, yoksa kart üzerinde fiziksel kısıt var mı?
5. **Yüz görseli boyutu**: JPEG kalite 80 + 320×240 (≈15–25 KB) tavsiye edilir. Onay?
6. **Çift çekirdek dağılımı**: Core 0 = GPS+LoRa, Core 1 = Kamera+UI. Onay?

## Fonksiyonel Gereksinimler

### 1. Boot
- WiFi/BT kapalı (güç tasarrufu).
- Tüm UART, I²C, SPI init.
- LoRa modülünü config moduna (M0=1, M1=1) alıp adres + kanal yaz, sonra normal moda (M0=0, M1=0).
- GPS warm-up bekle (en az 4 satellite fix).
- OLED'e "READY" yaz, LED yeşil.

### 2. Buton Kesmesi (FALLING edge)
- 50 ms debounce.
- Trigger handler `xTaskCreatePinnedToCore` ile Core 1'de görev planla.
- LED sarı (capture in progress).

### 3. GPS Yakalama (Core 0)
- NMEA `$GNGGA` veya `$GNRMC` cümlesini parse et (TinyGPSPlus kütüphanesi).
- Lat, Lon (float64), Alt (float32), HDOP, sat count, fix time topla.
- Fix yoksa veya HDOP > 2.0 → hata kodu döndür, OLED'e "GPS BAD" yaz.

### 4. Yüz Görüntü Yakalama (Core 1)
- Kamera `esp_camera_fb_get()` ile bir frame al.
- JPEG encode (kamera donanımı destekliyorsa direkt).
- Yüz tespiti ESP32'de **YAPILMAZ** — sadece raw JPEG gönderilir. Jetson tarafı yüz tanır.
- Hata varsa "CAM BAD" göster.

### 5. Paket Oluşturma (`shared/protocol/packet.h` referansı)
- Header (`magic`, `version`, `msg_type=TRIGGER`, `seq_num`)
- Payload: `[lat, lon, alt, hdop, sat_count, ts_unix, jpeg_len, jpeg_bytes...]`
- AES-128-CCM şifreleme (key: `shared/protocol/keys/lora.key` — derleme sırasında `partition` veya `nvs` ile ESP32'ye yaz)
- CRC-16/CCITT footer
- Toplam paket > LoRa MTU ise **chunk'la**: `MSG_TRIGGER_CHUNK` (`chunk_idx`, `total_chunks`)

### 6. LoRa İletim
- UART2 üzerinden chunk'ları sırayla gönder.
- Her chunk arası AUX pin LOW olana kadar bekle (modül busy).
- 3 retransmit denemesi (Jetson'dan ACK bekle, timeout 500 ms).
- ACK yoksa OLED "NO ACK" + LED kırmızı.

### 7. ACK Dinleme
- Jetson'dan gelen `MSG_ACK` paketini parse et (`seq_num` eşleşmeli).
- Sonra `MSG_TELEMETRY` paketleri (İHA durumu) gelir — OLED'de göster: mode, batarya %, mesafe.

### 8. OLED UI
- Üst: durum (READY / SENDING / ACK OK / MISSION ACTIVE / DELIVERED)
- Orta: GPS lat/lon, sat#
- Alt: İHA telemetri (mode, batarya, mesafe) — telemetri varsa

### 9. Failsafe / Manuel Abort
- Buton 3 saniye basılı tutulursa `MSG_ABORT` paketi gönder.

## Mimari (önerilen)
```
firmware/esp32_ground/
├── platformio.ini
├── src/
│   ├── main.cpp           # setup, loop, task scheduling
│   ├── gps_task.cpp
│   ├── camera_task.cpp
│   ├── lora_task.cpp
│   ├── ui_task.cpp
│   ├── crypto.cpp         # AES-CCM wrapper (mbedTLS)
│   └── packet_builder.cpp
├── include/
│   ├── pinout.h
│   ├── config.h
│   └── packet.h           # symlink veya copy: shared/protocol/packet.h
└── test/
    ├── test_packet_builder/
    └── test_crypto/
```

## Testler
- Unit: `test_packet_builder` (sahte GPS+yüz → byte array → CRC + AES doğrula)
- Unit: `test_crypto` (encrypt/decrypt round-trip)
- HIL: gerçek LoRa loopback → Jetson tarafında parse OK
- Field: GPS soğuk başlangıç < 60 s, sıcak < 5 s

## Kabul Kriterleri
- Buton → LoRa TX gecikme < 1 saniye (kamera dahil)
- Paket kayıp oranı < %5 (10 m mesafe, açık alan)
- 30 dakika sürekli çalışma, hafıza sızıntısı yok
- OLED 60 FPS güncellenmek zorunda değil; 5 Hz yeterli

## GÜÇLENDİRMELER (AUDIT)

### G1. JPEG Boyutu Optimizasyonu (KRİTİK — görev hızı)
Orijinal 320×240 RGB JPEG @ Q80 = 15–25 KB. 9.6 kbps LoRa'da 20–30 sn. **Kabul edilemez.** Fix:
- Yüzü kırp + resize **160×160 grayscale**, JPEG Q65 → **3–5 KB**.
- Sıkıştırılmış paket toplam 4–6 KB → ~5 saniye iletim.
- Yüz tespiti ESP32'de yapılmıyor — ortalama merkez crop (ped üzerinde yüz hep merkezde varsayılır).

### G2. GPS Time → RTC Sync
NEO-M8N NMEA `$GNRMC` cümlesinde UTC time. ESP32 RTC'sine yaz (`settimeofday()`). Bu sayede ESP32 logları Jetson + Pixhawk ile aynı zaman çizgisinde.

### G3. NVS Persistent Counter
LoRa seq counter NVS'te saklı. Boot'ta `nvs_get_u32("lora_seq") + 1000` ile sıçra. Nonce reuse önlemi (G1 modül 02).

### G4. Boot Beacon
Boot tamamlandığında ilk paket `MSG_BOOT` = `{ seq_start, fw_version }`. Jetson buradan seq pencereyi resync eder.

### G5. LoRa RSSI/SNR Telemetri
LoRa E32 AUX pin ve dahili register'lardan RSSI/SNR oku (kütüphane destekli), TELEMETRY payload'ına ekle.

### G6. Watchdog
ESP32 task watchdog timer enable, her task `esp_task_wdt_reset()` çağırır. Hung task → reboot.

### G7. Versiyon Pin
`platformio.ini`:
```ini
lib_deps =
    mikalhart/TinyGPSPlus @ ^1.0.3
    bodmer/TFT_eSPI @ ^2.5.43
    espressif/esp32-camera @ ^2.0.4
```

## Verme
- Tam çalışan PlatformIO projesi
- README: build (`pio run`), upload (`pio run -t upload`), monitor (`pio device monitor`)
- Pinout şeması (markdown tablo)
- Test raporu
