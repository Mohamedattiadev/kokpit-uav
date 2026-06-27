# 02 — LoRa PAKET PROTOKOLÜ (Shared Contract)

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`

> **Bu modül diğer tüm haberleşme modüllerinin TEK doğru kaynağıdır.** Burada üretilen `packet_spec.md`, `packet.h`, `packet.py` dosyalarına ESP32 (modül 01) ve Jetson LoRa RX (modül 03) bağlıdır. Önce bu modül bitmeden diğer haberleşme modülleri başlamamalı.

## Görev
LoRa E32 433T20D üzerinde çalışacak, AES-128-CCM şifreli, CRC-16 korumalı, sıralı, chunk-able bir mesaj protokolü tanımla ve hem C (ESP32) hem Python (Jetson) referans implementasyonunu yaz. Sözleşmeyi `shared/protocol/packet_spec.md`'ye dök.

## Açılışta Executor'a Sor (zorunlu)

1. **Şifreleme**: AES-128-CCM (tavsiye, integrity+confidentiality bir arada) mi, AES-128-GCM mi, sadece HMAC-SHA256 + plaintext mi?
2. **Anahtar yönetimi**: Tek statik pre-shared key (tavsiye, yarışma kapsamı için yeterli) mi, ECDH key exchange mi?
3. **MTU**: LoRa E32 maks payload 58 byte / paket (varsayılan config). Bunu kabul mu, modülü farklı configleyecek miyiz?
4. **Bitrate**: 2.4 kbps (varsayılan, en güvenli) mi, 9.6 kbps mi, 19.2 kbps mi?
5. **ACK stratejisi**: Stop-and-wait (her chunk için ACK, basit) mi, sliding window mu?
6. **Sequence number**: 4-byte monotonik (tavsiye) mi, 2-byte mı?

## Paket Yapısı (TAVSİYE — onay aldıktan sonra üret)

```
+--------+---------+----------+----------+---------+----------+----------+-------+
| MAGIC  | VERSION | MSG_TYPE | SEQ_NUM  | CHUNK   | TOT_CHK  | PAYLOAD  | CRC16 |
| 2 byte | 1 byte  | 1 byte   | 4 byte   | 1 byte  | 1 byte   | N byte   | 2 byte|
+--------+---------+----------+----------+---------+----------+----------+-------+
        |<------ HEADER (10 byte) ----->|        |<- ENCRYPTED ->|
```

- `MAGIC` = `0x4B50` ("KP" — Kokpit)
- `VERSION` = `0x01`
- `MSG_TYPE`:
  | Kod | Anlam |
  |---|---|
  | 0x01 | TRIGGER (yer→İHA, GPS+yüz) |
  | 0x02 | TRIGGER_CHUNK (büyük payload parçası) |
  | 0x03 | ACK |
  | 0x04 | NACK |
  | 0x05 | TELEMETRY (İHA→yer) |
  | 0x06 | ABORT (her iki yön) |
  | 0x07 | HEARTBEAT |
  | 0x08 | MISSION_STATUS (state machine event'leri) |
- `SEQ_NUM`: monoton artan, replay guard
- `CHUNK` / `TOT_CHK`: payload bir LoRa paketine sığmazsa chunk'lama
- `PAYLOAD`: AES-128-CCM ile şifreli. Nonce = `SEQ_NUM(4)` + `MSG_TYPE(1)` + `CHUNK(1)` + 6 byte zero pad. CCM tag (8 byte) payload sonuna eklenir.
- `CRC16`: CCITT (poly 0x1021, init 0xFFFF), tüm pakete (header dahil ama CRC hariç)

### Payload şemaları

**TRIGGER** (chunk reassembly sonrası):
```c
struct trigger_payload {
  uint32_t ts_unix;        // 4
  int32_t  lat_e7;         // 4  (1e-7 derece, MAVLink uyumlu)
  int32_t  lon_e7;         // 4
  int32_t  alt_mm;         // 4  (mm)
  uint16_t hdop_x100;      // 2
  uint8_t  sat_count;      // 1
  uint8_t  reserved;       // 1
  uint16_t jpeg_len;       // 2
  uint8_t  jpeg[];         // variable
};
```

**ACK**: `{ uint32_t acked_seq; uint8_t status; }` — status: 0=OK, 1=CRC_FAIL, 2=DECRYPT_FAIL, 3=BAD_VERSION

**TELEMETRY** (İHA→yer, 1 Hz):
```c
struct telemetry_payload {
  uint8_t  mode;           // GUIDED, AUTO, RTL, LAND...
  uint8_t  battery_pct;
  uint16_t altitude_m_x10; // 0.1 m
  int32_t  lat_e7;
  int32_t  lon_e7;
  uint16_t distance_to_home_m;
  uint8_t  mission_state;  // state machine enum
  uint8_t  flags;          // bit0=armed, bit1=gps_ok, bit2=marker_locked, bit3=face_verified
};
```

**MISSION_STATUS**: `{ uint8_t event_id; uint8_t param; }` — event: TAKEOFF, EN_ROUTE, MARKER_FOUND, FACE_OK, DELIVERED, RTL_START, LANDED, ABORT

## Referans Implementasyonlar

### `shared/protocol/packet.h` (C, ESP32 için)
- `packet_build()`, `packet_parse()`, `packet_encrypt()`, `packet_decrypt()`
- mbedTLS AES-CCM kullan
- CRC-16/CCITT yazılım implementasyonu (lookup table)

### `shared/protocol/packet.py` (Python, Jetson için)
- `cryptography` paketi (`AESCCM`) kullan
- Aynı API yüzeyi
- `dataclasses` ile payload struct'ları (Python `struct` modülü ile pack/unpack)

### `shared/protocol/keys/`
- `lora.key.example` (16 byte hex)
- `lora.key` `.gitignore`'lu — her dev local üretir (`openssl rand -hex 16`)
- Donanıma flash (ESP32 NVS) ve Jetson'da `~/.config/kokpit/lora.key` olarak yaz

## Testler
- `tests/test_roundtrip.py`: Python encode → C decode (HIL stub), C encode → Python decode
- `tests/test_chunking.py`: 10 KB JPEG payload → chunk → reassemble
- `tests/test_replay.py`: aynı SEQ_NUM iki kez gelirse ikincisi reject
- `tests/test_crc.py`: bilinen vektörlerle CRC doğrulama
- Fuzz: rastgele bit-flip → decrypt fail temiz hata döner

## Kabul Kriterleri
- ESP32 → Jetson aynı paketi bit-bit eşit decode
- Chunked 20 KB JPEG: < 8 saniye iletim @ 9.6 kbps
- Replay attack reject %100
- Bozuk paket → silent drop + log, crash yok

## GÜÇLENDİRMELER (AUDIT — uygulanması zorunlu)

### G1. Nonce Reuse Önleme (KRİTİK)
Sadece `seq_num` nonce kullanmak ESP32 reboot'ta felaket. Çözüm:
- ESP32 NVS'e seq counter yaz. Her boot'ta `nvs_seq += 1000` ileri sıçra. Boot beacon paketi (`MSG_BOOT`) Jetson'a yeni başlangıç noktasını bildirir.
- Alternatif olarak, **12-byte random nonce** her paketle gönder (payload önünde plaintext). Replay protection ayrı seq alanı ile.
- Tavsiye: persistent seq (basit) + boot beacon.

### G2. Payload Bütünlük Hash'i (KRİTİK)
Chunk-level CRC yeterli değil; chunk sıra hatası bütünlüğü bozar. TRIGGER payload'a:
```c
uint8_t payload_sha256[8];  // ilk 8 byte, header'dan hemen sonra, plaintext
```
Reassembly sonrası Jetson tarafı verify. Eşleşmezse drop + NACK.

### G3. Yeni Mesaj Tipleri
- `0x09 MSG_BOOT`: ESP32 boot beacon `{ uint32_t seq_start; uint32_t fw_version; }`
- `0x0A MSG_REF_EMBEDDING`: yüz JPEG yerine (opsiyonel mod) 512×float16 = 1024 byte embedding gönder — LoRa süresi 30 sn → 1 sn'ye iner. Jetson tarafı ESP32'nin embed çıkardığını varsayar (ESP32-CAM güçlü değilse skip)

### G4. Link Quality Telemetri
TELEMETRY payload'a ekle:
```c
int8_t  lora_rssi;     // dBm
int8_t  lora_snr;      // dB
uint8_t packet_loss_pct;
```

### G5. Versiyon Pin
`shared/protocol/CHANGELOG.md` zorunlu, MAGIC + VERSION değişimi backwards-incompat işareti.

## Verme
- `shared/protocol/packet_spec.md` (insan okunur sözleşme)
- `shared/protocol/packet.h` + `packet.c`
- `shared/protocol/packet.py`
- `shared/protocol/tests/`
- README: integration guide (modül 01 ve 03 için "şu fonksiyonu çağır" örnekleri)
