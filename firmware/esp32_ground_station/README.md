# firmware/esp32_ground_station/ — Yer İstasyonu (Ped) — ESP32

Sorumlu: **Attia** (protokol Arda ile ortak)

Yer ünitesi; NEO-M8N GPS'ten anlık koordinatı okur, yetkili alıcı kimliğini
seçer, fiziksel buton ile tetiklenince GPS + alıcı kimliğini CRC'li tek pakette
birleştirir ve LoRa E32 ile İHA'ya gönderir (rapor 3.3.1.1).

## Dosyalar
- `ground_station.ino` — ESP32 ana programı (Arduino).
- `packet_protocol.h` — İHA tarafı `onboard/packet_protocol.py` ile **birebir** aynı
  paket biçimi (CRC-16/CCITT, little-endian). Biri değişirse diğeri de değişmeli.

## Gerekli kütüphaneler (Arduino Library Manager)
- **TinyGPSPlus** (Mikal Hart) — GPS NMEA ayrıştırma
- **TFT_eSPI** (Bodmer) — TTGO T-Display ekran (`USE_TFT 1` ise). `User_Setup`'ta
  TTGO T-Display profili seçili olmalı.

## Örnek kablolama (kendi pinlerine göre `ground_station.ino` başında güncelle)

| Modül | Sinyal | ESP32 Pin |
|------|--------|-----------|
| NEO-M8N GPS | TX → ESP RX1 | GPIO25 |
| NEO-M8N GPS | RX ← ESP TX1 | GPIO26 |
| LoRa E32 | TX → ESP RX2 | GPIO27 |
| LoRa E32 | RX ← ESP TX2 | GPIO13 |
| LoRa E32 | M0 | GPIO12 |
| LoRa E32 | M1 | GPIO15 |
| LoRa E32 | AUX | GPIO2 |
| Buton | → GND | GPIO33 |
| Buzzer | + | GPIO32 |
| LED | + | GPIO17 |

> LoRa E32: normal (şeffaf) iletim için **M0=0, M1=0**. Kod bunu otomatik ayarlar.
> Verici ve alıcı E32 modüllerinin **kanal/adres/hava-hızı** ayarları AYNI olmalı.

## Kullanım
- **Kısa basış** → o anki GPS + seçili alıcı kimliği ile teslimat paketi gönderir
  (güvenilirlik için 3 kez). GPS fix yoksa **göndermez** (drone yanlış koordinata
  gitmesin).
- **Uzun basış (>1.5 sn)** → alıcı kimliğini döngüsel değiştirir (1..9).
- Ekran: GPS durumu, gönderim sonucu, seçili alıcı kimliği, gönderim sayacı.

## Biyometrik veri hakkında (önemli)
Tam yüz JPEG'ini LoRa üzerinden göndermek pratik değildir (saniyeler sürer).
Bu yüzden yer istasyonu **alıcı kimliği** (`recipient_id`) gönderir; İHA üzerinde
`faces/alici_<id>.jpg` referansları kayıtlıdır ve İHA hedefte gördüğü yüzü bu
referansla eşleştirir. OV5640 kamera, operatörün doğru alıcıyı seçmesi/onaylaması
için kullanılır. (Protokol, istenirse küçük thumbnail'in `FACE_CHUNK` ile parça
parça gönderilmesini de destekler — `onboard/packet_protocol.py`.)

## Doğrulama
Paket biçiminin İHA tarafıyla uyumu otomatik test edilmiştir: C (ESP32) ve Python
(Jetson) aynı baytları üretir. Değişiklik sonrası kontrol:
```bash
# C ve Python çıktısı aynı hex olmalı
gcc -O2 ctest.c -o ctest && ./ctest   # (test kodu ana README'de)
```
