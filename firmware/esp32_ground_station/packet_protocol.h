/*
 * packet_protocol.h — Kokpit LoRa paket protokolü (ESP32 tarafı)
 *
 * Bu dosya, drone/packet_protocol.py ile BİREBİR aynı bayt düzenini tanımlar.
 * Birini değiştirirsen diğerini de güncelle! (Aynı CRC, aynı struct sırası.)
 *
 * Bayt düzeni: little-endian. ESP32 (Xtensa) zaten little-endian'dır,
 * bu yüzden struct'ları doğrudan kopyalayabiliriz. __attribute__((packed))
 * ile derleyicinin hizalama eklemesini engelliyoruz.
 */
#ifndef KOKPIT_PACKET_PROTOCOL_H
#define KOKPIT_PACKET_PROTOCOL_H

#include <stdint.h>
#include <string.h>

#define KOKPIT_MAGIC0 0x4B  // 'K'
#define KOKPIT_MAGIC1 0x50  // 'P'
#define KOKPIT_PROTOCOL_VERSION 1
#define KOKPIT_HEADER_SIZE 6
#define KOKPIT_CRC_SIZE 2

// Mesaj tipleri (drone/packet_protocol.py MsgType ile aynı)
enum KokpitMsgType {
  MSG_DELIVERY_REQUEST = 1,
  MSG_FACE_CHUNK       = 2,
  MSG_ABORT            = 3,
  MSG_HEARTBEAT        = 4
};

// DELIVERY_REQUEST gövdesi (21 bayt). Python DELIVERY_FMT "<iiiHBBBI" ile aynı.
typedef struct __attribute__((packed)) {
  int32_t  lat_e7;        // derece * 1e7
  int32_t  lon_e7;        // derece * 1e7
  int32_t  alt_mm;        // metre * 1000 (AMSL)
  uint16_t recipient_id;  // yetkili alıcı kimliği
  uint8_t  gps_fix;       // 3 = 3D fix
  uint8_t  num_sats;
  uint8_t  flags;
  uint32_t timestamp_ms;
} DeliveryRequest;

// CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF) — Python crc16_ccitt ile aynı.
static inline uint16_t kokpit_crc16(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (int b = 0; b < 8; b++) {
      if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
      else              crc = (crc << 1);
    }
  }
  return crc;
}

/*
 * Bir paketi 'out' tamponuna çerçeveler. Dönüş: toplam bayt sayısı.
 * out en az (6 + payload_len + 2) bayt olmalı.
 */
static inline size_t kokpit_frame(uint8_t msg_type, uint8_t seq,
                                  const uint8_t *payload, uint8_t payload_len,
                                  uint8_t *out) {
  out[0] = KOKPIT_MAGIC0;
  out[1] = KOKPIT_MAGIC1;
  out[2] = KOKPIT_PROTOCOL_VERSION;
  out[3] = msg_type;
  out[4] = seq;
  out[5] = payload_len;
  if (payload_len && payload) memcpy(out + KOKPIT_HEADER_SIZE, payload, payload_len);
  // CRC: magic hariç (index 2'den itibaren) başlık + payload
  uint16_t crc = kokpit_crc16(out + 2, (size_t)(KOKPIT_HEADER_SIZE - 2) + payload_len);
  size_t crc_pos = KOKPIT_HEADER_SIZE + payload_len;
  out[crc_pos]     = (uint8_t)(crc & 0xFF);        // little-endian
  out[crc_pos + 1] = (uint8_t)((crc >> 8) & 0xFF);
  return crc_pos + KOKPIT_CRC_SIZE;
}

// DELIVERY_REQUEST paketini çerçeveler. out >= 29 bayt olmalı.
static inline size_t kokpit_frame_delivery(const DeliveryRequest *req,
                                           uint8_t seq, uint8_t *out) {
  return kokpit_frame(MSG_DELIVERY_REQUEST, seq,
                      (const uint8_t *)req, sizeof(DeliveryRequest), out);
}

#endif  // KOKPIT_PACKET_PROTOCOL_H
