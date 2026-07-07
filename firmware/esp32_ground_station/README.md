# firmware/esp32_ground_station/ — Yer İstasyonu (Ped) — ESP32

Sorumlu: **Attia** (protokol Arda ile ortak)

Yer ünitesi; NEO-M8N GPS'ten anlık koordinatı okur, yetkili alıcı kimliğini
seçer, fiziksel buton ile tetiklenince GPS + alıcı kimliğini CRC'li tek pakette
birleştirir ve LoRa E32 ile İHA'ya gönderir (rapor 3.3.1.1).

## Dosyalar
- `esp32_ground_station.ino` — ESP32 ana programı (Arduino). Dosya adı klasör
  adıyla aynı olmak zorunda (Arduino kuralı) — `arduino-cli`/Arduino IDE
  aksi halde sketch'i açamaz.
- `packet_protocol.h` — İHA tarafı `onboard/packet_protocol.py` ile **birebir** aynı
  paket biçimi (CRC-16/CCITT, little-endian). Biri değişirse diğeri de değişmeli.

## Gerekli kütüphaneler (Arduino Library Manager)

Versiyonlar bilerek sabitlendi — Library Manager güncellemesi sessizce
derleme hatası veya farklı davranışa yol açmasın diye (`AUDIT_GUCLENDIRMELER.md`
madde 12). Kurulumda **"Install specific version"** seçip aşağıdaki
sürümleri seç:

- **TinyGPSPlus** (Mikal Hart) — **v1.0.3** — GPS NMEA ayrıştırma
- **TFT_eSPI** (Bodmer) — **v2.5.43** — TTGO T-Display ekran (`USE_TFT 1` ise).
  `User_Setup`'ta TTGO T-Display profili seçili olmalı.

PlatformIO kullananlar için `platformio.ini`'de eşdeğeri:
```ini
lib_deps =
    mikalhart/TinyGPSPlus@1.0.3
    bodmer/TFT_eSPI@2.5.43
```

## Kablolama

Kod iki kart profilini destekler — `esp32_ground_station.ino` başındaki
`KOKPIT_BOARD` ile seçilir. **Default: `BOARD_ESP32CAM`** (tek kart, kamera dahili).

### Profil 1 — AI-Thinker ESP32-CAM (default, tek kart)

Kamera GPIO 0,5,18,19,21,22,23,25,26,27,32,34,35,36,39 pinlerini kullanır;
GPS/LoRa yalnızca kalan boş pinlere bağlanır:

| Modül | Sinyal | ESP32-CAM Pin |
|------|--------|-----------|
| NEO-M8N GPS | TX → ESP RX | GPIO13 |
| NEO-M8N GPS | RX | **bağlanmaz** (sadece okuma) |
| LoRa E32 | TX → ESP RX | GPIO14 |
| LoRa E32 | RX ← ESP TX | GPIO15 |
| LoRa E32 | M0 + M1 | **GND'ye sabit kablola** (şeffaf mod) |
| LoRa E32 | AUX | boşta |
| Buton | → GND | GPIO12 |
| Buzzer (ops.) | + | GPIO2 |
| LED | — | GPIO4 (karttaki flaş LED, ek kablo yok) |

> GPIO12 strapping pinidir: buton GND'ye çekildiği için boot güvenlidir,
> ama pine harici PULL-UP DİRENCİ TAKMA (yanlış flash voltajı seçtirir).
> ESP32-CAM'de USB yok — yüklemek için USB-TTL dönüştürücü gerekir
> (GPIO0'ı GND'ye çekerek boot moduna al, U0T/U0R çapraz bağla).

### Profil 2 — TTGO T-Display (`KOKPIT_BOARD BOARD_TTGO`, kamerasız)

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

> Bu profilde kamera pinleri GPS/LoRa ile çakıştığından **USE_CAMERA=1
> derlenmez** (bilinçli `#error`) — TTGO'da placeholder JPEG kullanılır.

> LoRa E32: normal (şeffaf) iletim için **M0=0, M1=0**. TTGO profili bunu
> koddan ayarlar; ESP32-CAM profilinde M0/M1 GND'ye sabit kablolanır.
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
