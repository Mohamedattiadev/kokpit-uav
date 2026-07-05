/*
 * packet_protocol.h — ESP32 yer istasyonu LoRa paket protokolü (v2)
 *
 * Python eşi: onboard/packet_protocol.py — bayt düzeni birebir aynı olmalı.
 *
 * v2 değişiklikleri:
 *   - 32-bit monotonik seq (NVS persistent, ESP32 reboot'ta wrap yok)
 *   - AES-128-CCM opsiyonel şifreleme (define KOKPIT_AES_ENABLED)
 *   - SHA-256 ilk 8 byte payload hash (mbedTLS)
 *   - FACE_IMAGE_BEGIN + FACE_IMAGE_CHUNK (yüz JPEG chunk'lı iletim)
 *   - BOOT_BEACON (Jetson'a seq başlangıç bildirme)
 *
 * Header (20 byte, little-endian):
 *   uint8  magic0=0x4B, uint8 magic1=0x50
 *   uint8  version=2
 *   uint8  msg_type
 *   uint32 seq
 *   uint8  chunk, uint8 total
 *   uint16 plen        (şifreli payload byte uzunluğu)
 *   uint8  sha8[8]     (plaintext SHA-256 ilk 8 byte)
 * Payload: N byte AES-CCM(plaintext) veya plaintext (AES disabled)
 * Footer: uint16 crc16/CCITT-FALSE  (header[2..end-2] üzerinden)
 */
#ifndef KOKPIT_PACKET_PROTOCOL_H
#define KOKPIT_PACKET_PROTOCOL_H

#include <Arduino.h>
#include <stdint.h>
#include <string.h>
#include "mbedtls/sha256.h"

#ifdef KOKPIT_AES_ENABLED
#include "mbedtls/ccm.h"
#endif

static constexpr uint8_t  PKT_MAGIC0       = 0x4B;
static constexpr uint8_t  PKT_MAGIC1       = 0x50;
static constexpr uint8_t  PKT_VERSION      = 2;
static constexpr size_t   PKT_HEADER_SIZE  = 20;
static constexpr size_t   PKT_CRC_SIZE     = 2;
static constexpr size_t   PKT_MAX_PAYLOAD  = 200;
static constexpr size_t   PKT_AES_TAG_LEN  = 8;

enum KokpitMsgType : uint8_t {
  MSG_BOOT_BEACON      = 0,
  MSG_DELIVERY_REQUEST = 1,
  MSG_FACE_IMAGE_BEGIN = 2,
  MSG_FACE_IMAGE_CHUNK = 3,
  MSG_ABORT            = 4,
  MSG_HEARTBEAT        = 5,
  MSG_TELEMETRY        = 6,
  MSG_ACK              = 7,
  MSG_MANUAL_REQUEST   = 8,
};

// DELIVERY_REQUEST gövdesi — 21 byte
struct __attribute__((packed)) DeliveryRequestBody {
  int32_t  lat_e7;
  int32_t  lon_e7;
  int32_t  alt_mm;
  uint16_t recipient_id;
  uint8_t  gps_fix;
  uint8_t  num_sats;
  uint8_t  flags;
  uint32_t timestamp_ms;
};

// FACE_IMAGE_BEGIN gövdesi — 22 byte
struct __attribute__((packed)) FaceBeginBody {
  int32_t  lat_e7;
  int32_t  lon_e7;
  int32_t  alt_mm;
  uint8_t  gps_fix;
  uint8_t  num_sats;
  uint16_t jpeg_len;
  uint16_t jpeg_total_chunks;
  uint32_t img_seq;
  uint32_t timestamp_ms;
};

// CRC-16/CCITT-FALSE
static inline uint16_t kokpit_crc16(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= ((uint16_t)data[i]) << 8;
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021)
                           : (uint16_t)(crc << 1);
    }
  }
  return crc;
}

static inline void kokpit_sha256_8(const uint8_t *data, size_t len,
                                   uint8_t out8[8]) {
  uint8_t hash[32];
  mbedtls_sha256(data, len, hash, 0);
  memcpy(out8, hash, 8);
}

#ifdef KOKPIT_AES_ENABLED
extern mbedtls_ccm_context g_kokpit_ccm;
extern bool g_kokpit_ccm_ready;

static inline bool kokpit_aes_init(const uint8_t key16[16]) {
  if (g_kokpit_ccm_ready) return true;
  mbedtls_ccm_init(&g_kokpit_ccm);
  int rc = mbedtls_ccm_setkey(&g_kokpit_ccm, MBEDTLS_CIPHER_ID_AES, key16, 128);
  g_kokpit_ccm_ready = (rc == 0);
  return g_kokpit_ccm_ready;
}

// Nonce 13 byte: seq32 (4) + msg_type (1) + chunk (1) + "KOKPIT0" (7)
static inline bool kokpit_aes_encrypt(uint32_t seq, uint8_t msg_type,
                                      uint8_t chunk,
                                      const uint8_t *pt, size_t pt_len,
                                      uint8_t *out, size_t *out_len) {
  if (!g_kokpit_ccm_ready) return false;
  uint8_t nonce[13];
  memcpy(nonce, &seq, 4);
  nonce[4] = msg_type;
  nonce[5] = chunk;
  memcpy(nonce + 6, "KOKPIT0", 7);
  int rc = mbedtls_ccm_encrypt_and_tag(
      &g_kokpit_ccm, pt_len, nonce, 13, nullptr, 0,
      pt, out, out + pt_len, PKT_AES_TAG_LEN);
  if (rc != 0) return false;
  *out_len = pt_len + PKT_AES_TAG_LEN;
  return true;
}

// kokpit_aes_encrypt'in tersi. ct_len tag dahil şifreli uzunluk; pt_len
// (çözülmüş) çıktısı ct_len - PKT_AES_TAG_LEN olur.
static inline bool kokpit_aes_decrypt(uint32_t seq, uint8_t msg_type,
                                      uint8_t chunk,
                                      const uint8_t *ct, size_t ct_len,
                                      uint8_t *out, size_t *pt_len) {
  if (!g_kokpit_ccm_ready) return false;
  if (ct_len < PKT_AES_TAG_LEN) return false;
  uint8_t nonce[13];
  memcpy(nonce, &seq, 4);
  nonce[4] = msg_type;
  nonce[5] = chunk;
  memcpy(nonce + 6, "KOKPIT0", 7);
  size_t data_len = ct_len - PKT_AES_TAG_LEN;
  int rc = mbedtls_ccm_auth_decrypt(
      &g_kokpit_ccm, data_len, nonce, 13, nullptr, 0,
      ct, out, ct + data_len, PKT_AES_TAG_LEN);
  if (rc != 0) return false;
  *pt_len = data_len;
  return true;
}
#endif

// ---------------------------------------------------------------------------
// TELEMETRY payload — onboard/packet_protocol.py TELEMETRY_FMT="<BHBbB" ile
// birebir aynı: mode_id, batt_mv, phase, rssi_dbm(signed), loss_pct
// ---------------------------------------------------------------------------
struct __attribute__((packed)) TelemetryBody {
  uint8_t  mode_id;
  uint16_t batt_mv;
  uint8_t  phase;
  int8_t   rssi_dbm;
  uint8_t  loss_pct;
};

// MANUAL_REQUEST payload — onboard/packet_protocol.py encode_manual_request:
// 16 byte ascii, null-padded (örn. "LOITER")
struct __attribute__((packed)) ManualRequestBody {
  char target_mode[16];
};

// ---------------------------------------------------------------------------
// Parsed paket (kokpit_pkt_build'in tersi çıktısı)
// ---------------------------------------------------------------------------
struct KokpitPacket {
  uint8_t  msg_type;
  uint32_t seq;
  uint8_t  chunk;
  uint8_t  total;
  uint8_t  payload[PKT_MAX_PAYLOAD];
  size_t   payload_len;
};

// ---------------------------------------------------------------------------
// KokpitStreamParser — UART bayt akışından paket ayıkla (Jetson tarafındaki
// StreamParser (onboard/packet_protocol.py) ile aynı mantık): magic resync,
// header/CRC doğrulama, AES-CCM decrypt, SHA-256 doğrulama, son 64 seq için
// replay koruması (LRU).
// ---------------------------------------------------------------------------
class KokpitStreamParser {
 public:
  static constexpr size_t BUF_CAP  = 300;   // >= HEADER(20)+MAX_PAYLOAD(200)+CRC(2)
  static constexpr size_t SEEN_CAP = 64;

  KokpitStreamParser() : len_(0), seen_pos_(0) {
    for (size_t i = 0; i < SEEN_CAP; i++) seen_[i] = 0xFFFFFFFFu;
    crc_errors = 0; sha_errors = 0; decrypt_errors = 0; replay_drops = 0;
    bytes_dropped = 0;
  }

  // Bir bayt besle. Tam ve geçerli bir paket oluşursa true döner ve `out`
  // doldurulur (BOOT_BEACON hariç replay kontrolünden de geçmiş olur).
  bool feed(uint8_t b, KokpitPacket *out) {
    if (len_ >= BUF_CAP) {
      // taşma koruması: en eski baytı at (senkron kaybı, resync ile düzelir)
      memmove(buf_, buf_ + 1, len_ - 1);
      len_--;
      bytes_dropped++;
    }
    buf_[len_++] = b;
    return tryExtract(out);
  }

  uint32_t crc_errors, sha_errors, decrypt_errors, replay_drops, bytes_dropped;

 private:
  uint8_t buf_[BUF_CAP];
  size_t  len_;
  uint32_t seen_[SEEN_CAP];
  size_t   seen_pos_;

  void dropOne() {
    if (len_ == 0) return;
    memmove(buf_, buf_ + 1, len_ - 1);
    len_--;
    bytes_dropped++;
  }

  bool seenContains(uint32_t seq) const {
    for (size_t i = 0; i < SEEN_CAP; i++) {
      if (seen_[i] == seq) return true;
    }
    return false;
  }

  void seenAdd(uint32_t seq) {
    seen_[seen_pos_] = seq;
    seen_pos_ = (seen_pos_ + 1) % SEEN_CAP;
  }

  bool tryExtract(KokpitPacket *out) {
    // Magic bulunana kadar baytları at
    while (len_ >= 2 && !(buf_[0] == PKT_MAGIC0 && buf_[1] == PKT_MAGIC1)) {
      dropOne();
    }
    if (len_ < PKT_HEADER_SIZE) return false;

    uint8_t version  = buf_[2];
    uint8_t msg_type = buf_[3];
    uint32_t seq; memcpy(&seq, buf_ + 4, 4);
    uint8_t chunk = buf_[8];
    uint8_t total = buf_[9];
    uint16_t plen; memcpy(&plen, buf_ + 10, 2);
    const uint8_t *sha_hdr = buf_ + 12;   // 8 byte

    if (plen > PKT_MAX_PAYLOAD) {
      dropOne();
      return false;
    }
    size_t frame_len = PKT_HEADER_SIZE + plen + PKT_CRC_SIZE;
    if (len_ < frame_len) return false;   // daha fazla bayt bekle

    uint16_t rx_crc; memcpy(&rx_crc, buf_ + frame_len - PKT_CRC_SIZE, 2);
    uint16_t calc_crc = kokpit_crc16(buf_ + 2, (PKT_HEADER_SIZE - 2) + plen);
    if (version != PKT_VERSION || rx_crc != calc_crc) {
      dropOne();
      crc_errors++;
      return false;
    }

    uint8_t payload_enc[PKT_MAX_PAYLOAD];
    memcpy(payload_enc, buf_ + PKT_HEADER_SIZE, plen);
    uint8_t sha_hdr_copy[8];
    memcpy(sha_hdr_copy, sha_hdr, 8);

    // Frame doğrulandı → tüketiliyor (kalan baytları öne kaydır)
    memmove(buf_, buf_ + frame_len, len_ - frame_len);
    len_ -= frame_len;

    uint8_t plaintext[PKT_MAX_PAYLOAD];
    size_t pt_len = plen;
#ifdef KOKPIT_AES_ENABLED
    if (g_kokpit_ccm_ready) {
      if (!kokpit_aes_decrypt(seq, msg_type, chunk, payload_enc, plen,
                              plaintext, &pt_len)) {
        decrypt_errors++;
        return false;
      }
    } else {
      memcpy(plaintext, payload_enc, plen);
      pt_len = plen;
    }
#else
    memcpy(plaintext, payload_enc, plen);
    pt_len = plen;
#endif

    uint8_t sha_calc[8];
    kokpit_sha256_8(plaintext, pt_len, sha_calc);
    if (memcmp(sha_calc, sha_hdr_copy, 8) != 0) {
      sha_errors++;
      return false;
    }

    if (msg_type != (uint8_t)MSG_BOOT_BEACON) {
      if (seenContains(seq)) {
        replay_drops++;
        return false;
      }
      seenAdd(seq);
    }

    out->msg_type = msg_type;
    out->seq = seq;
    out->chunk = chunk;
    out->total = total;
    out->payload_len = pt_len;
    memcpy(out->payload, plaintext, pt_len);
    return true;
  }
};

// Frame builder. Returns total bytes written, 0 on error.
// out_cap must be >= PKT_HEADER_SIZE + (pt_len + 8) + PKT_CRC_SIZE.
static inline size_t kokpit_pkt_build(uint8_t msg_type, uint32_t seq,
                                      uint8_t chunk, uint8_t total,
                                      const uint8_t *plaintext, size_t pt_len,
                                      uint8_t *out, size_t out_cap) {
  uint8_t enc_buf[PKT_MAX_PAYLOAD];
  size_t  enc_len = pt_len;
  const uint8_t *payload_src = plaintext;

#ifdef KOKPIT_AES_ENABLED
  if (g_kokpit_ccm_ready && pt_len + PKT_AES_TAG_LEN <= sizeof(enc_buf)) {
    if (kokpit_aes_encrypt(seq, msg_type, chunk, plaintext, pt_len,
                           enc_buf, &enc_len)) {
      payload_src = enc_buf;
    }
  }
#endif

  if (enc_len > PKT_MAX_PAYLOAD) return 0;
  size_t total_size = PKT_HEADER_SIZE + enc_len + PKT_CRC_SIZE;
  if (total_size > out_cap) return 0;

  uint8_t sha8[8];
  kokpit_sha256_8(plaintext, pt_len, sha8);

  size_t i = 0;
  out[i++] = PKT_MAGIC0;
  out[i++] = PKT_MAGIC1;
  out[i++] = PKT_VERSION;
  out[i++] = msg_type;
  out[i++] = (uint8_t)((seq >>  0) & 0xFF);
  out[i++] = (uint8_t)((seq >>  8) & 0xFF);
  out[i++] = (uint8_t)((seq >> 16) & 0xFF);
  out[i++] = (uint8_t)((seq >> 24) & 0xFF);
  out[i++] = chunk;
  out[i++] = total;
  out[i++] = (uint8_t)(enc_len & 0xFF);
  out[i++] = (uint8_t)((enc_len >> 8) & 0xFF);
  memcpy(out + i, sha8, 8); i += 8;
  memcpy(out + i, payload_src, enc_len); i += enc_len;

  uint16_t crc = kokpit_crc16(out + 2, (PKT_HEADER_SIZE - 2) + enc_len);
  out[i++] = (uint8_t)(crc & 0xFF);
  out[i++] = (uint8_t)((crc >> 8) & 0xFF);
  return i;
}

#endif  // KOKPIT_PACKET_PROTOCOL_H
