/*
 * ground_station.ino — Kokpit Yer İstasyonu (Ped) — ESP32 / TTGO T-Display
 * Sorumlu: Attia (+ Arda ile ortak protokol)
 *
 * GÖREV (rapor 3.3.1.1):
 *   1) NEO-M8N GPS'ten anlık koordinatı oku (UART, NMEA -> TinyGPS++)
 *   2) Yetkili alıcının kimliğini seç (OV5640 ile yüz/operatör onayı)
 *   3) Fiziksel buton ile tetikle
 *   4) GPS + alıcı kimliğini tek pakette birleştir (CRC'li)
 *   5) LoRa E32 433MHz ile İHA'ya gönder
 *   6) TTGO ekranında durum göster
 *
 * Donanım bağlantıları (ÖRNEK — kendi kablajına göre güncelle):
 *   NEO-M8N GPS : TX->GPIO25 (ESP RX1), RX->GPIO26 (ESP TX1), 9600 baud
 *   LoRa E32    : TX->GPIO27 (ESP RX2), RX->GPIO13 (ESP TX2), 9600 baud
 *                 M0->GPIO12, M1->GPIO15, AUX->GPIO2 (mod kontrolü)
 *   Buton       : GPIO33 -> GND  (INPUT_PULLUP, basınca LOW)
 *   Buzzer      : GPIO32
 *   LED         : GPIO17
 *   TFT (TTGO)  : TFT_eSPI kütüphanesi User_Setup'ta TTGO seçili olmalı
 *
 * Kütüphaneler (Arduino Library Manager):
 *   - TinyGPSPlus  (Mikal Hart)
 *   - TFT_eSPI     (Bodmer)  [USE_TFT tanımlıysa]
 */

#include <Arduino.h>
#include "packet_protocol.h"

// ----------------- DERLEME SEÇENEKLERİ -----------------
#define USE_TFT 1        // TTGO ekranı kullan (TFT_eSPI gerekli)
#define USE_GPS 1        // 0 yaparsan sabit test koordinatı gönderir

// ----------------- PİN TANIMLARI -----------------
static const int PIN_GPS_RX = 25;   // ESP RX <- GPS TX
static const int PIN_GPS_TX = 26;   // ESP TX -> GPS RX
static const int PIN_LORA_RX = 27;  // ESP RX <- LoRa TX
static const int PIN_LORA_TX = 13;  // ESP TX -> LoRa RX
static const int PIN_LORA_M0 = 12;
static const int PIN_LORA_M1 = 15;
static const int PIN_LORA_AUX = 2;
static const int PIN_BUTTON = 33;
static const int PIN_BUZZER = 32;
static const int PIN_LED = 17;

// ----------------- AYARLAR -----------------
static const uint32_t GPS_BAUD = 9600;
static const uint32_t LORA_BAUD = 9600;
static const uint16_t DEFAULT_RECIPIENT_ID = 7;  // faces/alici_7.jpg ile eşleşir
static const uint32_t RESEND_COUNT = 3;          // paketi 3 kez yolla (güvenilirlik)
static const uint32_t RESEND_GAP_MS = 200;

// ----------------- GLOBALLER -----------------
#include <TinyGPSPlus.h>
TinyGPSPlus gps;
HardwareSerial GpsSerial(1);
HardwareSerial LoraSerial(2);

#if USE_TFT
#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();
#endif

uint16_t recipientId = DEFAULT_RECIPIENT_ID;
uint8_t seqCounter = 0;
uint32_t lastButtonMs = 0;
uint32_t packetsSent = 0;

// ----------------- YARDIMCI -----------------
void beep(int ms) {
  digitalWrite(PIN_BUZZER, HIGH);
  digitalWrite(PIN_LED, HIGH);
  delay(ms);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_LED, LOW);
}

void setLoraMode(bool config) {
  // M0=0,M1=0 -> normal (transparent) iletim; M0=1,M1=1 -> uyku/konfig
  digitalWrite(PIN_LORA_M0, config ? HIGH : LOW);
  digitalWrite(PIN_LORA_M1, config ? HIGH : LOW);
  delay(50);
}

#if USE_TFT
void drawStatus(const char *line1, const char *line2, uint16_t color) {
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_CYAN, TFT_BLACK);
  tft.setTextSize(2);
  tft.setCursor(4, 4);
  tft.print("KOKPIT YER IST.");
  tft.setTextColor(color, TFT_BLACK);
  tft.setCursor(4, 36);
  tft.print(line1);
  tft.setCursor(4, 64);
  tft.print(line2);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextSize(1);
  tft.setCursor(4, 110);
  tft.printf("Alici ID: %u  Gond: %lu", recipientId, packetsSent);
}
#else
void drawStatus(const char *l1, const char *l2, uint16_t) {
  Serial.printf("[STATUS] %s | %s\n", l1, l2);
}
#endif

// GPS verisini topla (çağrı başına kısa süre)
void feedGps(uint32_t ms) {
  uint32_t start = millis();
  while (millis() - start < ms) {
    while (GpsSerial.available()) gps.encode(GpsSerial.read());
  }
}

// Teslimat talebini hazırla ve LoRa ile gönder
void sendDeliveryRequest() {
  DeliveryRequest req;
  memset(&req, 0, sizeof(req));

#if USE_GPS
  if (gps.location.isValid() && gps.satellites.value() >= 6) {
    req.lat_e7 = (int32_t)(gps.location.lat() * 1e7);
    req.lon_e7 = (int32_t)(gps.location.lng() * 1e7);
    req.alt_mm = (int32_t)(gps.altitude.meters() * 1000.0);
    req.gps_fix = 3;
    req.num_sats = (uint8_t)gps.satellites.value();
  } else {
    drawStatus("GPS FIX YOK", "Gonderim iptal", TFT_RED);
    beep(60); delay(80); beep(60);
    return;  // FIX yoksa GÖNDERME (drone yanlış koordinata gitmesin!)
  }
#else
  // Test koordinatı (Ankara YBÜ civarı)
  req.lat_e7 = (int32_t)(39.942000 * 1e7);
  req.lon_e7 = (int32_t)(32.847000 * 1e7);
  req.alt_mm = 900000;
  req.gps_fix = 3;
  req.num_sats = 12;
#endif

  req.recipient_id = recipientId;
  req.flags = 0;
  req.timestamp_ms = millis();

  uint8_t buf[64];
  // Paketi birkaç kez gönder — LoRa tek yönlü, ACK yok; tekrar = güvenilirlik
  for (uint32_t i = 0; i < RESEND_COUNT; i++) {
    size_t n = kokpit_frame_delivery(&req, seqCounter, buf);
    LoraSerial.write(buf, n);
    LoraSerial.flush();
    delay(RESEND_GAP_MS);
  }
  seqCounter++;
  packetsSent++;

  char l1[32], l2[32];
  snprintf(l1, sizeof(l1), "GONDERILDI x%lu", (unsigned long)RESEND_COUNT);
  snprintf(l2, sizeof(l2), "%.5f,%.5f", req.lat_e7 / 1e7, req.lon_e7 / 1e7);
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
  setLoraMode(false);  // normal iletim modu

#if USE_TFT
  tft.init();
  tft.setRotation(1);
#endif
  drawStatus("HAZIR", "Butona bas -> gonder", TFT_YELLOW);
  beep(80);
  Serial.println("Kokpit yer istasyonu hazir.");
}

void loop() {
  feedGps(50);

  // Buton: kısa basış -> gönder. (İstersen uzun basış ile alıcı ID değiştir.)
  if (digitalRead(PIN_BUTTON) == LOW && (millis() - lastButtonMs) > 800) {
    lastButtonMs = millis();
    uint32_t pressStart = millis();
    while (digitalRead(PIN_BUTTON) == LOW) {
      feedGps(10);
      if (millis() - pressStart > 1500) break;  // uzun basış
    }
    if (millis() - pressStart > 1500) {
      // UZUN BASIŞ: alıcı kimliğini döngüsel artır (1..9)
      recipientId = (recipientId % 9) + 1;
      drawStatus("ALICI DEGISTI", "", TFT_ORANGE);
      beep(40);
    } else {
      // KISA BASIŞ: teslimat talebini gönder
      drawStatus("GONDERILIYOR...", "", TFT_YELLOW);
      sendDeliveryRequest();
    }
  }

  // Periyodik GPS durum güncelle
  static uint32_t lastUi = 0;
  if (millis() - lastUi > 1000) {
    lastUi = millis();
    if (digitalRead(PIN_BUTTON) == HIGH) {  // gönderim ekranını ezmesin
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
