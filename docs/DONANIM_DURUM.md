# Donanım Durumu — Kalan İşler (Ekip İçin Özet)

> Bu dosya `docs/DONANIM_PLANI.md`'nin **özeti** — sadece hâlâ ⬜ (yapılmamış)
> olan maddeleri, kim yapacak ve tam olarak nasıl yapacak şeklinde tek yerde
> topluyor. Tüm komutların ve arka plan açıklamalarının detayı için
> `docs/DONANIM_PLANI.md`'deki ilgili İŞ bölümüne bak — burası sadece
> "şimdi ne yapmam lazım" sorusuna hızlı cevap için.
>
> **Yazılım tarafı tamamen bitti** (369 test yeşil, CI yeşil). Aşağıdakilerin
> hiçbiri kod yazmayı gerektirmiyor — hepsi fiziksel donanım + saha işi.

---

## İŞ-1 — TensorRT (kod ✅ tamam, 2 fiziksel adım kaldı)

**Kim:** Jetson'a sudo erişimi olan biri (donanım/sistem sorumlusu).
**Süre:** ~15 dakika.

1. **Performans modu aç:**
   ```bash
   sudo nvpmodel -m 0        # MAXN moduna al (varsayılan düşük güç modu yavaş kalır)
   sudo jetson_clocks        # saat hızlarını sabitle
   nvpmodel -q                # doğrula: "MAXN" veya "15W" dönmeli
   ```
2. **Servisi aktif et** (`kokpit-mc.service` içindeki `WorkingDirectory` satırını
   gerçek repo yoluna göre düzenle, örn. `/home/<kullanıcı>/kokpit-uav`):
   ```bash
   cd <repo-yolu>
   sudo cp systemd/kokpit-mc.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now kokpit-mc
   journalctl -u kokpit-mc -f     # WATCHDOG=1 + paket logları görünmeli
   ```

Detay/sorun giderme: `docs/DONANIM_PLANI.md` → İŞ-1 → Adım 1.7.

---

## İŞ-2 — Kamera + Lidar Extrinsics Kalibrasyon (hiç başlanmadı)

**Kim:** Mekanik + elektronik ekibi.
**Süre:** 1-2 saat. Kamera/lidar yeri her değiştiğinde tekrarlanmalı.
**Önkoşul:** Gövde tamamlanmış, kamera + lidar fiziksel monte edilmiş.

**Neden önemli:** Kamera/lidar gövde merkezinden ölçülmeden yazılıma
beslenirse hassas iniş 5-10 cm yana kayar. Rapor hedefi ±14 cm.

**Adımlar:**
1. Drone'u su terazisiyle düz bir zemine koy, burnu (x+ yönü) sabit bir
   noktaya baksın.
2. **Kamera offsetini ölç** (Pixhawk'ın tam altı = referans nokta):
   - `cam.x`: Pixhawk'tan lens merkezine **ileri** mesafe (m) — lens önde ise +
   - `cam.y`: sağa kayma (m) — sağda ise +
   - `cam.z`: lens **aşağı** mesafe (m), aşağıda olduğu için hep +
   - `cam.roll/pitch/yaw`: lens tam aşağı bakıyorsa 0,0,0; eğikse açıölçerle derece ölç
3. **Lidar offsetini ölç** (aynı mantık, lidar ışın çıkış noktası referans):
   `lidar.x/y/z` aynı şekilde.
4. **Kalibrasyon aracını çalıştır** (Jetson'da):
   ```bash
   cd <repo-yolu> && source .venv/bin/activate
   python3 tools/calibrate_extrinsics.py
   # Sırayla soracağı CAM x/y/z ve LIDAR x/y/z değerlerini metre cinsinden gir
   # -> onboard/configs/extrinsics.yaml yazılır
   ```
5. **Doğrula:**
   ```bash
   cat onboard/configs/extrinsics.yaml
   KOKPIT_SIM=1 pytest tests/test_extrinsics.py -v
   ```

**Doğrulama checklist'i:**
- [ ] Drone su terazisiyle düz konumda ölçüldü
- [ ] Tüm ölçüler **metre** cinsinden (cm değil!)
- [ ] `onboard/configs/extrinsics.yaml` oluştu
- [ ] `load_extrinsics()` doğru değerleri okuyor
- [ ] Sonraki uçuş testinde marker iniş hatası ±14 cm içinde

**Sık hatalar:** negatif değerlerde işaret unutma (`-0.05`, nokta kullan
virgül değil); iniş hâlâ kayıyorsa ölçüyü rüzgarsız/kapalı alanda tekrar al;
lidar 0 m okuyorsa bu kalibrasyon değil, `RNGFND1_TYPE` param sorunu.

Detay: `docs/DONANIM_PLANI.md` → İŞ-2.

---

## İŞ-3 — ESP32 (kod ✅ tamam, 3 fiziksel adım kaldı)

**Kim:** Elektronik/firmware ekibi.
**Süre:** yarım gün.

1. **Firmware'i gerçek ESP32 kartına yükle** — Arduino IDE veya PlatformIO
   + USB. Kütüphane listesi: `firmware/esp32_ground_station/README.md`.
2. **Gerçek LoRa E32 üzerinden loopback testi:** Jetson ↔ ESP32 arası 100
   paket gönder, kayıp oranını ölç, %0 kayıp hedefle (kablosuz saha
   koşullarında biraz kayıp normal, ama sürekli >%30 loss varsa anten/mesafe
   kontrol et — RSSI < -100dBm veya loss > %30'da buzzer zaten uyaracak).
3. **TFT ekranı gerçek ışıkta/açıda okunabilirliğini kontrol et** (MODE+BATT,
   PHASE, RSSI+LOSS 3 satırı).

Detay: `docs/DONANIM_PLANI.md` → İŞ-3 (madde 494-497).

---

## İŞ-4 — Param Yükleme + Saha Test Uçuşları (hiç başlanmadı)

**Kim:** Zeki Emir (uçuş kontrolcüsü) + tüm takım.
**Süre:** ~2 gün (yarım gün param, 1.5 gün uçuş kademe).
**Önkoşul:** İŞ-1, İŞ-2, İŞ-3 bitmiş; drone tam montajlı; batarya şarjlı.

### Adım 4.1 — Param Yükle (Mission Planner)

CONFIG → Full Parameter Tree'den `ardupilot/` klasöründeki 7 dosyayı
**sırayla** yükle, her birinden sonra **Write Params** + Pixhawk reboot:

```
01_initial_setup.param       (frame class, motor sayısı)
02_radio_calibration.param   (RC channel min/max)
03_battery_failsafe.param    (voltaj eşikleri)
04_geofence.param            (yarışma alanı sınırı)
05_compass_calibration.param
06_lidar_rangefinder.param   (TFmini RNGFND1)
07_precland.param            (PRECLAND PID)
```

### Adım 4.2 — Kalibrasyon Turu (zorunlu, saha öncesi)

1. Accelerometer cal (Initial Setup → Accel)
2. Compass cal (8 yönlü döndürme)
3. Radio cal (RC stick min/max)
4. ESC cal (motor sırası + yön)
5. Lidar test (Status → sonarrange canlı değişmeli)
6. Geofence test (manual'de sınıra yaklaş → RTL tetiklenmeli)

### Adım 4.3 — Kademeli Uçuş Testleri (açık alan)

**Her adımda başarısız olursan dur, sebebini bulmadan ileri gitme.**

```
1) MANUAL hover        — pilot stick, 1m, 30sn. Tilt/drift normal mi?
2) STABILIZE hover      — aynı test, otomatik leveling çalışıyor mu?
3) LOITER hover         — GPS hold, 1dk, drift < 1m olmalı
4) RTL test             — LOITER'dan RTL'e al, otomatik dönüş+iniş
5) GUIDED waypoint      — Flight Plan'de 50m waypoint, GUIDED + auto execute
6) Otonom görev         — KOKPIT_SIM=0 python3 -m onboard.mission
                          (veya systemd servisi) — ESP32 buton bas, tam akış
```

### Adım 4.4 — PID Tune (gerekirse)

Adım 3'te osilasyon/gevşeklik varsa: Extended Tuning → RC7'ye AUTOTUNE ata →
LOITER'da kalkış → AUTOTUNE switch → 5-10 dk uçuş → LAND → Save Params.

**Doğrulama checklist'i:**
- [ ] 7 param dosyası yüklü + Write Params yapıldı
- [ ] Compass + accel + radio + ESC kalibrasyonları tamam
- [ ] Lidar canlı veri veriyor
- [ ] Geofence ihlali → RTL tetikliyor
- [ ] Adım 1-5 sorunsuz tamamlandı
- [ ] Otonom görev test uçuşu başarılı (5 ardışık deneme)
- [ ] Marker iniş ortalama hatası < 20 cm

**Sık hatalar:** dairesel sallanma (toilet bowl) → compass'ı metalden uzakta
tekrar kalibre et; GPS fix yok → RC/GPS antenlerini ayrı kollara al; LOITER'da
sürüklenme → HDOP<1.5 bekle, EKF reset; otonom takeoff başlamıyor →
`STATUSTEXT` mesajını oku (pre-arm fail); servo paket bırakmıyor →
`SERVO9_FUNCTION=0 SERVO9_MIN=1100 MAX=1900`.

Detay: `docs/DONANIM_PLANI.md` → İŞ-4.

---

## Saha Test Öncesi Final Kontrol (İŞ-4 bitince, her uçuş öncesi)

- [ ] Batarya tam şarjlı (>24V, 6S) + yedek batarya hazır
- [ ] Manual + Stabilize + Loiter + Guided modları test edildi
- [ ] Geofence yüklü ve aktif
- [ ] Telemetri linki + RC link kontrol edildi
- [ ] Rüzgar < 5 m/s, yağmur yok (`tools/weather_check.py` ile kontrol edilebilir)
- [ ] Yarıçap 100m içinde insan yok
- [ ] Yangın söndürücü hazır
- [ ] Pilot sertifikalı + dinlenmiş

---

## Sıra Önerisi

İŞ-1 ve İŞ-3'ün kalan fiziksel adımları (kısa, birkaç saat) paralel
yapılabilir. İŞ-2 (kalibrasyon) İŞ-4'ün **önkoşulu** — kalibrasyon
yapılmadan otonom iniş testine geçilmemeli. İŞ-4 en son ve en uzun süren
iş, diğer üçü bitmeden başlamayın.
