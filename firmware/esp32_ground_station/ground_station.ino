/*
 * ground_station.ino — Kokpit Yer İstasyonu (Ped) — ESP32 / TTGO T-Display (v2)
 * Sorumlu: Attia (+ Arda, Zeki ile ortak protokol)
 *
 * GÖREV (rapor 3.3.1.1 — FACE IMAGE CAPTURE → packet → drone):
 *   1) NEO-M8N GPS'ten anlık koordinatı oku
 *   2) Buton tetiklenince OV5640 kamerasından alıcı yüzünü yakala (JPEG)
 *   3) GPS + yüz JPEG'ini şifreli + chunk'lı LoRa paketinde drone'a gönder
 *   4) TTGO ekranında durum göster
 *
 * v2 değişiklikleri (Sprint 0+1+2):
 *   - 32-bit monotonik seq, NVS persistent (her boot'ta +1000 sıçra)
 *   - Boot beacon: ilk paket Jetson'a seq başlangıç noktasını bildirir
 *   - FACE_IMAGE_BEGIN + N x FACE_IMAGE_CHUNK iletim akışı
 *   - AES-128-CCM şifreleme (KOKPIT_AES_ENABLED + NVS'te 16 byte key)
 *   - SHA-256 payload bütünlük hash
 *
 * Donanım (örnek pinout — kendi karta göre güncelle):
 *   NEO-M8N GPS : TX->GPIO25, RX->GPIO26, 9600 baud
 *   LoRa E32    : TX->GPIO27, RX->GPIO13, 9600 baud
 *                 M0->GPIO12, M1->GPIO15, AUX->GPIO2
 *   Buton       : GPIO33 (INPUT_PULLUP)
 *   Buzzer/LED  : GPIO32/17
 *   OV5640      : ESP32-CAM modülünde standart pinout (esp_camera kütüphanesi)
 *
 * Kütüphaneler:
 *   - TinyGPSPlus    (Mikal Hart)
 *   - TFT_eSPI       (Bodmer, TTGO ekran)
 *   - esp32-camera   (Espressif — OV5640/OV2640 driver)
 *   - Preferences    (NVS, ESP32 dahili)
 *   - mbedTLS        (ESP-IDF içinde, dahili)
 */

#include <Arduino.h>
#include <Preferences.h>
#include <sys/time.h>
#include <time.h>
#include "packet_protocol.h"

// ----------------- DERLEME SEÇENEKLERİ -----------------
#define USE_TFT 1
#define USE_GPS 1
#define USE_CAMERA 1          // 0 → kameradan değil, placeholder JPEG kullan
// #define KOKPIT_AES_ENABLED  // packet_protocol.h içinde aktifleştirilir
                              // anahtarı NVS'te "kokpit/aes_key" altına yaz

#ifdef KOKPIT_AES_ENABLED
mbedtls_ccm_context g_kokpit_ccm;
bool g_kokpit_ccm_ready = false;
#endif

// ----------------- PİN TANIMLARI -----------------
static const int PIN_GPS_RX = 25;
static const int PIN_GPS_TX = 26;
static const int PIN_LORA_RX = 27;
static const int PIN_LORA_TX = 13;
static const int PIN_LORA_M0 = 12;
static const int PIN_LORA_M1 = 15;
static const int PIN_LORA_AUX = 2;
static const int PIN_BUTTON = 33;
static const int PIN_BUZZER = 32;
static const int PIN_LED = 17;

// ----------------- AYARLAR -----------------
static const uint32_t GPS_BAUD = 9600;
static const uint32_t LORA_BAUD = 9600;
static const size_t   FACE_CHUNK_PAYLOAD = 100;   // her chunk içindeki JPEG byte sayısı
                                                  // (header + AES tag + CRC sığacak şekilde)
static const uint32_t SEQ_BOOT_JUMP = 1000;       // her boot'ta seq +1000
static const uint32_t INTER_CHUNK_MS = 80;        // chunk'lar arası bekleme (LoRa AUX)
static const uint32_t FW_VERSION = 0x0200;        // v2

// ----------------- GLOBALLER -----------------
#include <TinyGPSPlus.h>
TinyGPSPlus gps;
HardwareSerial GpsSerial(1);
HardwareSerial LoraSerial(2);

#if USE_TFT
#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();
#endif

#if USE_CAMERA
#include "esp_camera.h"
// ESP32-CAM AI-Thinker pinout (gerekirse kendi modülüne göre güncelle)
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
#endif

Preferences prefs;
uint32_t g_seq = 0;            // monoton 32-bit seq (NVS persistent)
uint32_t g_img_seq = 0;        // yüz görüntüsü için ayrı uniq id
uint32_t packetsSent = 0;
uint32_t lastButtonMs = 0;
uint16_t recipientId = 7;       // legacy mode için (kullanılırsa)

// ----------------- YARDIMCI -----------------
void beep(int ms) {
  digitalWrite(PIN_BUZZER, HIGH); digitalWrite(PIN_LED, HIGH);
  delay(ms);
  digitalWrite(PIN_BUZZER, LOW); digitalWrite(PIN_LED, LOW);
}

void setLoraMode(bool config) {
  digitalWrite(PIN_LORA_M0, config ? HIGH : LOW);
  digitalWrite(PIN_LORA_M1, config ? HIGH : LOW);
  delay(50);
}

uint32_t nextSeq() {
  g_seq++;
  // NVS'e nadiren yaz (her 50'de bir flash aşınmasını azalt)
  if (g_seq % 50 == 0) {
    prefs.putUInt("seq", g_seq);
  }
  return g_seq;
}

#if USE_TFT
void drawStatus(const char *l1, const char *l2, uint16_t color) {
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_CYAN, TFT_BLACK);
  tft.setTextSize(2); tft.setCursor(4, 4);
  tft.print("KOKPIT YER IST.");
  tft.setTextColor(color, TFT_BLACK);
  tft.setCursor(4, 36); tft.print(l1);
  tft.setCursor(4, 64); tft.print(l2);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextSize(1); tft.setCursor(4, 110);
  tft.printf("seq:%u  gond:%u", g_seq, packetsSent);
}
#else
void drawStatus(const char *l1, const char *l2, uint16_t) {
  Serial.printf("[STATUS] %s | %s\n", l1, l2);
}
#endif

void feedGps(uint32_t ms) {
  uint32_t start = millis();
  while (millis() - start < ms) {
    while (GpsSerial.available()) gps.encode(GpsSerial.read());
  }
}

#if USE_CAMERA
bool initCamera() {
  camera_config_t cfg = {};
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.ledc_timer   = LEDC_TIMER_0;
  cfg.pin_d0 = Y2_GPIO_NUM; cfg.pin_d1 = Y3_GPIO_NUM;
  cfg.pin_d2 = Y4_GPIO_NUM; cfg.pin_d3 = Y5_GPIO_NUM;
  cfg.pin_d4 = Y6_GPIO_NUM; cfg.pin_d5 = Y7_GPIO_NUM;
  cfg.pin_d6 = Y8_GPIO_NUM; cfg.pin_d7 = Y9_GPIO_NUM;
  cfg.pin_xclk = XCLK_GPIO_NUM;
  cfg.pin_pclk = PCLK_GPIO_NUM;
  cfg.pin_vsync = VSYNC_GPIO_NUM;
  cfg.pin_href = HREF_GPIO_NUM;
  cfg.pin_sscb_sda = SIOD_GPIO_NUM;
  cfg.pin_sscb_scl = SIOC_GPIO_NUM;
  cfg.pin_pwdn = PWDN_GPIO_NUM;
  cfg.pin_reset = RESET_GPIO_NUM;
  cfg.xclk_freq_hz = 20000000;
  cfg.frame_size = FRAMESIZE_QQVGA;   // 160x120 (yakın 160x160 için crop)
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.jpeg_quality = 25;              // ~Q65 eşdeğeri (düşük = yüksek kalite)
  cfg.fb_count = 1;
  return esp_camera_init(&cfg) == ESP_OK;
}

// Kameradan JPEG yakala. Buffer caller'a aittir (esp_camera_fb_return ile iade et).
camera_fb_t* captureFace() {
  // İlk frame'i at (eski/karanlık olabilir), sonraki frame'i kullan
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb) esp_camera_fb_return(fb);
  fb = esp_camera_fb_get();
  return fb;
}
#endif

// N9 — MAC son 32 bit'inden station_id türet (hot swap detect)
uint32_t getStationId() {
  uint8_t mac[6];
  esp_efuse_mac_get_default(mac);
  return ((uint32_t)mac[2] << 24) | ((uint32_t)mac[3] << 16) |
         ((uint32_t)mac[4] << 8)  | ((uint32_t)mac[5]);
}

// Boot beacon: Jetson'a yeni seq başlangıç noktasını + station_id bildir
void sendBootBeacon() {
  uint8_t payload[12];
  uint32_t seq_start = g_seq;
  uint32_t station_id = getStationId();
  memcpy(payload, &seq_start, 4);
  memcpy(payload + 4, &FW_VERSION, 4);
  memcpy(payload + 8, &station_id, 4);
  uint8_t buf[64];
  size_t n = kokpit_pkt_build(MSG_BOOT_BEACON, seq_start, 0, 1,
                              payload, sizeof(payload), buf, sizeof(buf));
  LoraSerial.write(buf, n);
  LoraSerial.flush();
  Serial.printf("[BOOT] beacon seq_start=%u fw=0x%04X station=0x%08X (%u byte)\n",
                seq_start, FW_VERSION, station_id, n);
}

bool fillGps(int32_t *lat_e7, int32_t *lon_e7, int32_t *alt_mm,
             uint8_t *sats, uint8_t *fix) {
#if USE_GPS
  if (gps.location.isValid() && gps.satellites.value() >= 6) {
    *lat_e7 = (int32_t)(gps.location.lat() * 1e7);
    *lon_e7 = (int32_t)(gps.location.lng() * 1e7);
    *alt_mm = (int32_t)(gps.altitude.meters() * 1000.0);
    *sats   = (uint8_t)gps.satellites.value();
    *fix    = 3;
    return true;
  }
  return false;
#else
  *lat_e7 = (int32_t)(39.942000 * 1e7);
  *lon_e7 = (int32_t)(32.847000 * 1e7);
  *alt_mm = 900000;
  *sats = 12; *fix = 3;
  return true;
#endif
}

// Yüz görüntülü teslimat — yeni mod (rapor uyumu)
void sendFaceDelivery() {
  int32_t lat_e7, lon_e7, alt_mm;
  uint8_t sats, fix;
  if (!fillGps(&lat_e7, &lon_e7, &alt_mm, &sats, &fix)) {
    drawStatus("GPS FIX YOK", "Gonderim iptal", TFT_RED);
    beep(60); delay(80); beep(60);
    return;
  }

#if USE_CAMERA
  camera_fb_t *fb = captureFace();
  if (!fb || fb->len == 0) {
    drawStatus("KAMERA HATA", "yuz alinamadi", TFT_RED);
    if (fb) esp_camera_fb_return(fb);
    return;
  }
  const uint8_t *jpeg_data = fb->buf;
  size_t jpeg_len = fb->len;
#else
  // Placeholder JPEG (gerçek kamera yoksa, test için minik byte dizisi)
  static const uint8_t fake_jpeg[] = {
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 'J','F','I','F', 0xFF, 0xD9
  };
  const uint8_t *jpeg_data = fake_jpeg;
  size_t jpeg_len = sizeof(fake_jpeg);
#endif

  uint16_t total_chunks = (uint16_t)((jpeg_len + FACE_CHUNK_PAYLOAD - 1) /
                                     FACE_CHUNK_PAYLOAD);
  if (total_chunks == 0) total_chunks = 1;
  g_img_seq++;

  // 1) FACE_IMAGE_BEGIN
  FaceBeginBody fb_body = {};
  fb_body.lat_e7 = lat_e7;
  fb_body.lon_e7 = lon_e7;
  fb_body.alt_mm = alt_mm;
  fb_body.gps_fix = fix;
  fb_body.num_sats = sats;
  fb_body.jpeg_len = (uint16_t)jpeg_len;
  fb_body.jpeg_total_chunks = total_chunks;
  fb_body.img_seq = g_img_seq;
  fb_body.timestamp_ms = millis();

  uint8_t buf[256];
  uint32_t base_seq = nextSeq();
  size_t n = kokpit_pkt_build(MSG_FACE_IMAGE_BEGIN, base_seq, 0, 1,
                              (uint8_t*)&fb_body, sizeof(fb_body),
                              buf, sizeof(buf));
  LoraSerial.write(buf, n); LoraSerial.flush();
  delay(INTER_CHUNK_MS);

  // 2) FACE_IMAGE_CHUNK x N (her chunk payload: [img_seq:u32] + data)
  uint8_t chunk_payload[FACE_CHUNK_PAYLOAD + 4];
  for (uint16_t i = 0; i < total_chunks; i++) {
    size_t off = (size_t)i * FACE_CHUNK_PAYLOAD;
    size_t this_len = (jpeg_len - off > FACE_CHUNK_PAYLOAD)
                          ? FACE_CHUNK_PAYLOAD : (jpeg_len - off);
    memcpy(chunk_payload, &g_img_seq, 4);
    memcpy(chunk_payload + 4, jpeg_data + off, this_len);
    uint32_t cseq = nextSeq();
    n = kokpit_pkt_build(MSG_FACE_IMAGE_CHUNK, cseq, (uint8_t)i,
                         (uint8_t)total_chunks,
                         chunk_payload, this_len + 4,
                         buf, sizeof(buf));
    LoraSerial.write(buf, n); LoraSerial.flush();
    delay(INTER_CHUNK_MS);
  }

#if USE_CAMERA
  esp_camera_fb_return(fb);
#endif

  packetsSent++;
  // Seq counter'ı kalıcı kaydet
  prefs.putUInt("seq", g_seq);

  char l1[32], l2[32];
  snprintf(l1, sizeof(l1), "GONDERILDI %u ck", total_chunks);
  snprintf(l2, sizeof(l2), "%.5f,%.5f", lat_e7 / 1e7, lon_e7 / 1e7);
  drawStatus(l1, l2, TFT_GREEN);
  beep(150);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_LORA_M0, OUTPUT);
  pinMode(PIN_LORA_M1, OUTPUT);
  pinMode(PIN_LORA_AUX, INPUT);

  GpsSerial.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
  LoraSerial.begin(LORA_BAUD, SERIAL_8N1, PIN_LORA_RX, PIN_LORA_TX);
  setLoraMode(false);

  // NVS'ten persistent seq yükle + boot jump
  prefs.begin("kokpit", false);
  g_seq = prefs.getUInt("seq", 0);
  g_seq += SEQ_BOOT_JUMP;
  prefs.putUInt("seq", g_seq);
  g_img_seq = prefs.getUInt("imgseq", 0);

#ifdef KOKPIT_AES_ENABLED
  // AES anahtarını NVS'ten yükle (binary 16 byte)
  uint8_t key[16];
  size_t klen = prefs.getBytes("aes_key", key, 16);
  if (klen == 16) {
    if (kokpit_aes_init(key)) {
      Serial.println("[CRYPTO] AES-128-CCM aktif");
    } else {
      Serial.println("[CRYPTO] AES init basarisiz, plaintext mode");
    }
  } else {
    Serial.println("[CRYPTO] AES anahtari NVS'te yok, plaintext mode");
  }
#endif

#if USE_TFT
  tft.init(); tft.setRotation(1);
#endif
#if USE_CAMERA
  if (!initCamera()) {
    Serial.println("[CAM] init basarisiz");
  }
#endif

  drawStatus("HAZIR", "Butona bas", TFT_YELLOW);
  beep(80);
  Serial.printf("[SETUP] seq=%u img_seq=%u\n", g_seq, g_img_seq);

  // Boot beacon — Jetson seq pencereyi resync etsin
  delay(200);
  sendBootBeacon();
}

void loop() {
  feedGps(50);

  // GPS UTC alındığında settimeofday — Jetson/Pixhawk ile log korelasyonu.
  static bool g_time_set = false;
  if (!g_time_set && gps.date.isValid() && gps.time.isValid() &&
      gps.date.year() > 2024) {
    struct tm tm = {};
    tm.tm_year = gps.date.year() - 1900;
    tm.tm_mon  = gps.date.month() - 1;
    tm.tm_mday = gps.date.day();
    tm.tm_hour = gps.time.hour();
    tm.tm_min  = gps.time.minute();
    tm.tm_sec  = gps.time.second();
    time_t epoch = mktime(&tm);
    struct timeval tv = { epoch, (suseconds_t)(gps.time.centisecond() * 10000L) };
    settimeofday(&tv, nullptr);
    g_time_set = true;
  }

  if (digitalRead(PIN_BUTTON) == LOW &&
      (millis() - lastButtonMs) > 800) {
    lastButtonMs = millis();
    uint32_t pressStart = millis();
    while (digitalRead(PIN_BUTTON) == LOW) {
      feedGps(10);
      if (millis() - pressStart > 1500) break;
    }
    if (millis() - pressStart > 1500) {
      // UZUN BASIŞ: ABORT paketi gönder
      uint8_t buf[32];
      uint32_t s = nextSeq();
      size_t n = kokpit_pkt_build(MSG_ABORT, s, 0, 1,
                                  nullptr, 0, buf, sizeof(buf));
      LoraSerial.write(buf, n); LoraSerial.flush();
      drawStatus("ABORT GONDERILDI", "", TFT_ORANGE);
      beep(40); delay(40); beep(40);
    } else {
      drawStatus("YAKALANIYOR...", "", TFT_YELLOW);
      sendFaceDelivery();
      // Her gönderim sonrası img_seq'i kalıcı kaydet
      prefs.putUInt("imgseq", g_img_seq);
    }
  }

  // 1 Hz GPS durum
  static uint32_t lastUi = 0;
  if (millis() - lastUi > 1000) {
    lastUi = millis();
    if (digitalRead(PIN_BUTTON) == HIGH) {
      char l1[32], l2[32];
      if (gps.location.isValid()) {
        snprintf(l1, sizeof(l1), "GPS OK sat:%lu",
                 (unsigned long)gps.satellites.value());
        snprintf(l2, sizeof(l2), "%.5f,%.5f",
                 gps.location.lat(), gps.location.lng());
        drawStatus(l1, l2, TFT_GREEN);
      } else {
        drawStatus("GPS bekleniyor...", "Acik alana cik", TFT_YELLOW);
      }
    }
  }
}
