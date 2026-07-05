// harness_main.cpp — ESP32 firmware'indeki packet_protocol.h'yi host (g++)
// üzerinde derleyip gerçek kart olmadan doğrulamak için CLI harness.
//
// Kullanım: harness <hex_bytes>
//   hex_bytes stdin'den byte byte KokpitStreamParser'a beslenir; her
//   çıkan geçerli paket için tek satır: "PKT msg=<n> seq=<n> chunk=<n>
//   total=<n> payload=<hex>" yazdırılır. Sonda sayaçlar: "STATS crc=<n>
//   sha=<n> decrypt=<n> replay=<n> dropped=<n>".
//
// KOKPIT_AES_ENABLED tanımlı DEĞİL: onboard/packet_protocol.py'de AES key
// dosyası yoksa (varsayılan dev/test ortamı) plaintext fallback moduyla
// birebir eşleşir.
#include "../../firmware/esp32_ground_station/packet_protocol.h"
#include <cstdio>
#include <string>
#include <vector>

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: %s <hex_bytes>\n", argv[0]);
    return 2;
  }
  std::string hex = argv[1];
  std::vector<uint8_t> bytes;
  for (size_t i = 0; i + 1 < hex.size(); i += 2) {
    int hi = hexval(hex[i]), lo = hexval(hex[i + 1]);
    if (hi < 0 || lo < 0) { fprintf(stderr, "bad hex\n"); return 2; }
    bytes.push_back((uint8_t)((hi << 4) | lo));
  }

  KokpitStreamParser parser;
  for (uint8_t b : bytes) {
    KokpitPacket pkt;
    if (parser.feed(b, &pkt)) {
      printf("PKT msg=%u seq=%u chunk=%u total=%u payload=",
             pkt.msg_type, pkt.seq, pkt.chunk, pkt.total);
      for (size_t i = 0; i < pkt.payload_len; i++) {
        printf("%02x", pkt.payload[i]);
      }
      printf("\n");
    }
  }
  printf("STATS crc=%u sha=%u decrypt=%u replay=%u dropped=%u\n",
         parser.crc_errors, parser.sha_errors, parser.decrypt_errors,
         parser.replay_drops, parser.bytes_dropped);
  return 0;
}
