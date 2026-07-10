# Bağlantı ve Durum — Görev Sadeleştirme Oturumu (Attia'ya)

> Bu dosya, yarışma günü kararıyla görevin sadeleştirilmesi için yapılan kod
> değişikliklerini ve geriye kalan fiziksel/donanım işlerini anlatır. Terim
> açıklamaları için `docs/DONANIM_DURUM.md`'ye bak — burada onları
> tekrarlamıyorum, sadece bu oturuma özgü olanı anlatıyorum.
>
> **Yazılım tarafında ne değişti (özet):** (1) hedef GPS artık yer
> istasyonundan değil bilgisayardan/Jetson'dan veriliyor, (2) yer istasyonu
> LoRa'sı görev akışının kritik yolundan çıkarıldı (kod SİLİNMEDİ, sadece
> bağımlılık kaldırıldı), (3) tek ArUco marker doğrulandı + PNG üretildi,
> (4) biyometrik doğrulama yarışma günü için bypass'landı, (5) pakete
> kumandadan (RC6) da elle erişim eklendi. Aşağıda hepsi detaylı.

---

## 1) Tam Bağlantı Şeması

| Bağlantı | Ne | Durum |
|---|---|---|
| Pixhawk **TELEM1** | Radyo telemetri (SiK radio) → yer kontrol istasyonu / Mission Planner | Değişmedi |
| Pixhawk **TELEM2** | Jetson (companion link, MAVLink) | `onboard/config.py` `LinkConfig.mavlink_real="/dev/ttyTHS1"` ile uyumlu — **DOĞRULA** (kablo TELEM2'ye takılı mı, Jetson tarafında doğru UART pini mi) |
| Pixhawk **SERIAL4** (varsayım — bkz. açık soru) | Lidar (Benewake TFS20-L mesafe sensörü), **Pixhawk'a DOĞRUDAN seri kabloyla** | `ardupilot/kokpit_lidar.param` bu oturumda düzeltildi (bkz. madde 2.3 aşağıda) |
| Jetson **CAM0 (CSI)** | Arducam 12MP IMX708 Fixed Focus HDR kamera | `onboard/config.py` yorum satırı düzeltildi; kalibrasyon YENİDEN yapılmalı (bkz. madde 3.2) |
| Servo (paket bırakma) | AUX1 / SERVO9 varsayımı (kod tarafı bunu kullanıyor) | **AÇIK SORU — fiziksel yeri netleşmedi**, bkz. madde 3.3 |
| Kumanda (RC) **RC6** | **YENİ:** manuel paket bırakma switch'i | Bu oturumda kod tarafında eklendi, bkz. madde 2.5 |
| Kumanda (RC) RC7 | MOTOR KILL (değişmedi) | `docs/DONANIM_DURUM.md`'de tanımlı |
| Kumanda (RC) RC8 | Pilot mod override (değişmedi, `RC8_OPTION`) | `ardupilot/kokpit_baseline.param` |

**Not — RC6 çakışma uyarısı:** `docs/DONANIM_DURUM.md` (Adım 4) önceden "gerekirse
boş bir kumanda koluna (örneğin RC6) AUTOTUNE ata" diyordu. Bu öneri artık
**GEÇERSİZ** — RC6 bu oturumla birlikte kalıcı olarak manuel paket bırakmaya
ayrıldı. AUTOTUNE gerekirse RC10 kullan (RC6'yı KULLANMA — aksi halde tuning
sırasında yanlışlıkla paket bırakma tetiklenebilir).

---

## 2) Ne Yapıldı (kod tarafı, bu oturum)

### 2.1 Madde 1 — Hedef GPS artık bilgisayardan/Jetson'dan

**Dosya:** `onboard/target_source.py` (yeni).

Yer istasyonundaki GPS modülü arızalı olduğu için hedef koordinat artık LoRa
ile değil, doğrudan komut satırından/ortam değişkeninden/bir dosyadan
okunuyor. Öncelik sırası:

1. CLI argümanı: `python3 -m onboard.mission --target-lat 39.9255 --target-lon 32.8663`
2. Ortam değişkeni: `KOKPIT_TARGET_LAT` / `KOKPIT_TARGET_LON` (+ opsiyonel
   `KOKPIT_TARGET_ALT`, `KOKPIT_TARGET_RECIPIENT`)
3. `onboard/configs/target.yaml` dosyası (şablon zaten repoda, yorum satırı
   açıp değerleri doldurman yeterli)

`onboard/mission.py` `main()` fonksiyonu artık kalkıştan önce bu üçünden
birini bulmak ZORUNDA — gerçek uçuşta (`KOKPIT_SIM=0`) hiçbiri yoksa program
**hata verip başlamıyor** (bilinçli sert hata — hedefsiz kalkış olmasın diye).

**Uçuş öncesi hedefi nasıl ayarlarsın (systemd servisiyle çalışıyorsa):**

```bash
sudo mkdir -p /etc/kokpit
sudo tee /etc/kokpit/target_gps > /dev/null <<'EOF'
KOKPIT_TARGET_LAT=39.925533
KOKPIT_TARGET_LON=32.866287
EOF
sudo systemctl restart kokpit-mc
```

`systemd/kokpit-mc.service` bu dosyayı otomatik yükleyecek şekilde
güncellendi (`EnvironmentFile=-/etc/kokpit/target_gps`). Dosya yoksa servis
başlamaz (Restart=on-failure ile döngüye girer, journalctl'de neden
göreceksin) — bu kasıtlı, hedefsiz kalkışı engellemek için.

### 2.2 Madde 2 — Yer istasyonu tamamen göstermelik

**Dosya:** `onboard/mission.py` (`_do_wait_packet`).

`Mission` artık kurucuya (`Mission(target=...)`) hedef verilmişse LoRa'yı hiç
beklemeden direkt kalkışa geçiyor. LoRa/ESP32 kodu (`onboard/lora_receiver.py`,
`onboard/packet_protocol.py`, `firmware/esp32_ground_station/`) **silinmedi**
— hem ileride geri dönülebilsin hem de mevcut test paketi (paket protokolü,
CRC, replay koruması, hot-swap gibi donanım-bağımsız testler) hâlâ çalışsın
diye. Sadece görev akışının ona bağımlı olması kaldırıldı: `main()` gerçek
uçuşta target'ı `target_source.py` ile bulup Mission'a veriyor, bu yüzden
`_do_wait_packet`'in LoRa bekleyen dalı gerçek uçuşta **hiç çalışmaz** —
sadece testlerde (LoRa enjeksiyonuyla eski davranışı doğrulayan testler hâlâ
geçerli, bkz. `tests/test_mission_integration.py`) kullanılır.

Yer istasyonu (ESP32) fiziksel olarak masada durabilir, ama gerçek uçuşta
ondan gelen hiçbir paket görev akışını etkilemez.

### 2.3 Madde 3 — Tek ArUco marker

**Dosya:** değişiklik gerekmedi, sadece doğrulandı + üretildi.

`onboard/config.py` `ArucoConfig.target_id = 0`, `dictionary = "DICT_5X5_100"`,
`marker_length_m = 0.30` zaten tek sabit markera ayarlıydı — kontrol edildi,
doğru.

`ped_marker.png` (repo kök dizini) bu oturumda yeniden üretildi:
```bash
python3 tools/generate_aruco.py --id 0 --dict DICT_5X5_100 --size 800 --out ped_marker.png
```
**Yazdırırken fiziksel kenar uzunluğunu tam 30 cm yap** — `marker_length_m`
ile birebir eşleşmeli, aksi halde ArUco'nun mesafe tahmini yanlış çıkar (ölçek
hatası doğrudan mesafeye yansır).

### 2.4 Madde 4 — Biyometrik doğrulama bypass

**Dosyalar:** `onboard/config.py` (`FaceConfig.verification_bypassed`),
`onboard/face_verifier.py` (`verify_with_voting`), `onboard/mission.py`
(`Mission.__init__`).

`FaceConfig`'e `verification_bypassed: bool = False` eklendi — varsayılan
**False** kaldı (mevcut yüz tanıma birim testleri gerçek eşleştirme mantığını
hâlâ test ediyor, onları bozmamak için). `Mission` kendi `FaceVerifier`'ını
**bypass'lı** (`verification_bypassed=True`) kuruyor — yani gerçek uçuşta
kayıtlı tek alıcı kim olursa olsun kamerada görülen HERHANGİ bir yüz PASS
sayılıyor. Kodda net şekilde işaretlendi (`# KASITLI: yarışma günü
basitleştirme kararı (madde 4)... BUG DEĞİLDİR`).

`faces/alici_0.jpg` altına tek bir kişinin referans fotoğrafı yüklenmeli
(hangi ID: `0`, `target_source.py`'nin `recipient_id` varsayılanıyla uyumlu).
Bypass açık olduğu için bu fotoğraf pratikte KİMİN olduğu önemli değil, ama
`setup()` sırasında "kayıtlı yüz yok" uyarısını susturmak için en az bir
dosya olsun.

### 2.5 Servo / Kumanda (RC) entegrasyonu

**Dosyalar:** `onboard/mavlink_interface.py` (RC_CHANNELS mesajı dinleme),
`onboard/package_dropper.py` (`manual_release()`), `onboard/mission.py`
(`_check_manual_rc_drop`), `onboard/config.py` (`DropperConfig.manual_rc_*`).

**Tasarım kararı:** RC kanalını Jetson yazılımı okuyup `manual_release()`
çağırıyor (ArduCopter'ın kendi native RCx→Servo passthrough'u YERİNE).
Gerekçe:

- Servo çıkışı (`SERVO9_FUNCTION=0`) zaten script/MAVLink kontrolünde —
  otomatik bırakma bunu kullanıyor. ArduCopter'da TEK bir servo çıkışı aynı
  anda hem "script kontrolü" hem "RCx passthrough" fonksiyonu OLAMAZ; ikisini
  aynı anda istiyorsak (otomatik VE manuel aynı fiziksel çıkışa), yazılım
  tarafında birleştirmek gerekiyor.
- **Dezavantaj (dürüstçe not düşülüyor):** Jetson yazılımı çökerse/donarsa bu
  manuel tetikleme de çalışmaz — native RCx passthrough olsaydı Jetson'dan
  bağımsız çalışırdı. Bu risk kabul edildi çünkü zaten TÜM otomatik teslimat
  akışı (ArUco, yüz, PID) Jetson'a bağımlı — Jetson çökerse zaten paket
  otomatik bırakılamaz, pilot STABILIZE'a geçip elle inebilir (RC7 kill /
  RC8 override hâlâ native ve Jetson'dan bağımsız çalışır, can güvenliği
  etkilenmez). Paketin manuel bırakılamaması can güvenliği riski değil,
  sadece görev/skor riski.
- RC6 seçildi (RC7=kill, RC8=mod override zaten dolu; RC9 sayı olarak
  SERVO9 ile karışmasın diye kasıtlı atlandı).

**Davranış:** `mission.py`'deki failsafe döngüsü (0.2 sn periyot) her turda
RC6 PWM değerini okur; `>=1700 us` ise ve daha önce tetiklenmemişse (edge
-triggered — switch'i açıp kapatmadan tekrar tetiklemez) `dropper.
manual_release()` çağrılır. Bu, FSM fazından/yüz doğrulamadan/marker
kilidinden BAĞIMSIZ çalışır (pilot görsel olarak karar veriyor) ama irtifa
(1.0–3.5 m) ve eğim (<15°) guard'ları HÂLÂ geçerli — fiziksel güvenlik
atlanamaz.

### 2.6 Lidar param düzeltmesi

**Dosya:** `ardupilot/kokpit_lidar.param`.

Eskiden `RNGFND1_TYPE=10` (MAVLink DISTANCE_SENSOR — Jetson'ın lidar'ı
Pixhawk'a MAVLink ile beslediği varsayımı) yazıyordu. Ama lidar **Pixhawk
SERIAL4/5'e doğrudan seri kabloyla bağlı** (ekipten kesin bilgi) — Jetson
araya girmiyor. Kontrol ettim: `onboard/mavlink_interface.py` zaten hiç
`DISTANCE_SENSOR` mesajı GÖNDERMİYORDU (kod tarafında bu param'ın varsaydığı
yol hiç kullanılmamış); Jetson sadece ArduCopter'ın yayınladığı `RANGEFINDER`
mesajını dinliyor — bu, sensörün kaynağı MAVLink mi native seri mi olduğuna
bakmaksızın ArduCopter'ın HER durumda yaptığı bir şey. Yani **Jetson tarafında
kod değişikliği gerekmedi**, sadece param dosyası düzeltildi:

```
SERIAL4_PROTOCOL,9      # Lidar
SERIAL4_BAUD,115        # 115200
RNGFND1_TYPE,27         # BenewakeTF03 ailesi (TFS20-L dahil)
RNGFND1_MIN_CM,20       # sensör spec: min 0.20 m
```

Kaynak: [ardupilot.org — Benewake TF02-Pro/TF03/TFS20-L rangefinder](https://ardupilot.org/copter/docs/common-benewake-tf02-lidar.html).

**AÇIK SORU — bkz. madde 3.1 aşağıda:** port SERIAL4 mü SERIAL5 mi kesinleşmedi.

---

## 3) Ne Yapılması Gerekiyor (fiziksel/donanım — Attia + ekip)

### 3.1 Lidar port teyidi (SERIAL4 mü SERIAL5 mi?)

`ardupilot/kokpit_lidar.param` şu an **SERIAL4** varsayıyor. Pixhawk'taki
lidar kablosunun hangi porta takılı olduğunu fiziksel olarak kontrol et
(port üzerinde genelde "SERIAL4" / "SERIAL5" yazar). SERIAL5'e takılıysa
dosyadaki `SERIAL4_PROTOCOL` ve `SERIAL4_BAUD` satırlarını `SERIAL5_PROTOCOL`
/ `SERIAL5_BAUD` olarak değiştir, sonra `tools/param_yukle.py` ile tekrar
yükle.

Ayrıca lidar modelinin gerçekten **Benewake TFS20-L** olduğunu teyit et —
farklı bir Benewake modeliyse `RNGFND1_TYPE` değişebilir (TFmini/TFmini-S
serisi = 20, TF02/orijinal TF02 = 19, TF02-Pro/TF03/TFS20-L/TF-Luna/TF-Nova/
TF350 = 27 — şu an 27 kullanılıyor, TFS20-L varsayımıyla).

### 3.2 Kamera kalibrasyonu (IMX708 ile YENİDEN)

`onboard/config.py`'deki `fx/fy/cx/cy` değerleri eski IMX219 kamerası
içindi — IMX708 için YANLIŞ. Saha öncesi mutlaka:
```bash
python3 tools/calibrate_camera.py
```
ile gerçek IMX708 kamerasından yeni `camera_calibration.npz` üret. Bu
yapılmadan ArUco mesafe tahmini (ve dolayısıyla hassas iniş ±14 cm hedefi)
güvenilir olmaz.

Ayrıca `gst-launch-1.0 nvarguscamerasrc sensor-id=0 !
'video/x-raw(memory:NVMM),width=1280,height=720' ! nvvidconv ! xvimagesink`
ile IMX708'in Jetson'da görüntü verdiğini doğrula (device tree/driver farklı
sensör için farklı olabilir).

### 3.3 Servo fiziksel bağlantı yeri (AÇIK SORU — ekip henüz karar vermedi)

Servonun Pixhawk'ta hangi çıkışa bağlanacağı ekip içinde netleşmemiş
("Bu servoyu da nereye ekleyeceğiz bi soralım"). Kod tarafında `SERVO9`
(AUX1) varsayımı var (`onboard/config.py` `DropperConfig.servo_channel=9`,
`ardupilot/kokpit_servo.param`) — mantıklı bir varsayılan ama **fiziksel
teyit gerekiyor**. Karar verilince:
1. Servo motoru gerçekten AUX1'e bağla (veya farklı bir AUX çıkışıysa
   `DropperConfig.servo_channel`'ı ve `kokpit_servo.param`'daki
   `SERVO9_*` satırlarını o kanala göre güncelle).
2. RC6 manuel switch'i de test et (bkz. madde 4 kontrol listesi).

### 3.4 ArUco marker'ı bas + pede yerleştir

`ped_marker.png` (repo kök dizini) 30 cm kenar uzunluğuyla yazdırılmalı
(fiziksel kenar `config.aruco.marker_length_m=0.30` ile TAM eşleşmeli) ve
pedin üzerine sabitlenmeli.

### 3.5 `faces/alici_0.jpg` referans fotoğrafı

Bypass açık olsa da `setup()` sırasındaki uyarıyı susturmak ve ileride
bypass geri alınırsa hazır olmak için `faces/` altına en az bir referans
fotoğraf (`alici_0.jpg`) koy.

---

## 4) Uçuş Öncesi Bağlantı Kontrol Listesi

- [ ] Pixhawk açık, TELEM1 (yer istasyonu/Mission Planner) ve TELEM2 (Jetson)
      kabloları takılı
- [ ] SERIAL4 (veya SERIAL5 — madde 3.1'e göre) lidar kablosu takılı,
      `param_yukle.py` ile güncel param'lar yüklendi
- [ ] Jetson servisi çalışıyor: `systemctl status kokpit-mc` (aktif/running)
- [ ] `/etc/kokpit/target_gps` dosyası GÜNCEL hedef koordinatla dolduruldu
      (bkz. madde 2.1) — eski/yanlış koordinat kalmadığından emin ol
- [ ] Kamera görüntü veriyor (dashboard'da veya `nvarguscamerasrc` testinde)
- [ ] Lidar canlı mesafe okuyor (Mission Planner Status ekranında değer
      değişiyor, sıfırda takılı kalmıyor)
- [ ] Servo test hareketi yapıldı: `MAV_CMD_DO_SET_SERVO` ile PWM 1100→1900→1100
      (kilitli → açık → kilitli) — Mission Planner'ın "Do Set Servo" aracıyla
      elle tetiklenebilir
- [ ] **RC6 manuel switch testi**: kumandada RC6'yı yukarı al, servo PWM'in
      değiştiğini gözlemle (uçmadan önce, yerde, paket TAKMADAN test et)
- [ ] `ped_marker.png` doğru boyutta (30 cm) basılı ve pede sabitlenmiş
- [ ] `faces/alici_0.jpg` mevcut (bypass açık olsa da uyarı vermesin diye)
- [ ] ArUco marker'ın altı/üzeri ile hizalı, ışık koşulları uygun

---

## 5) İlgili Mevcut Araçlar (tekrar yazılmadı, hâlâ geçerli)

- `docs/DONANIM_DURUM.md` — genel donanım kurulum rehberi (İŞ-1 Jetson
  kurulumu, İŞ-2 extrinsics kalibrasyonu **değişmedi**)
- `scripts/is1_jetson_kurulum.sh` — Jetson tam güç modu + systemd kurulumu
- `scripts/is2_extrinsics_kalibrasyon.sh` — kamera/lidar montaj offseti
- `tools/param_yukle.py` — 7 param dosyasını (artık düzeltilmiş
  `kokpit_lidar.param` dahil) Pixhawk'a MAVLink üzerinden yükler
- `tools/lora_paket_testi.py` — LoRa paket sayma/kayıp testi (İŞ-3 artık
  göstermelik olsa da, donanımın kendisi çalışıyor mu diye test etmek
  istersen hâlâ kullanılabilir — sadece görev akışına bağlı değil)
- `tools/calibrate_camera.py` — kamera kalibrasyonu (IMX708 ile TEKRAR yap)
- `tools/generate_aruco.py` — ArUco marker üretimi

---

## 6) Doğrulama Durumu (dürüstçe)

- ✅ `KOKPIT_SIM=1 python3 -m pytest tests/ -q` — yeni davranışlar için
  testler eklendi (`tests/test_target_source.py`,
  `tests/test_biometric_bypass.py`, `tests/test_manual_rc_drop.py`,
  `tests/test_manual_release_guards.py`,
  `tests/test_mission_target_source_integration.py`), mevcut testler
  korunmaya çalışıldı.
- ✅ `simulation/run_sitl.sh` ile ArduCopter SITL'e karşı uçtan uca deneme
  yapıldı (bu bölüm test sonuçlarıyla birlikte güncellenecek).
- ❌ **Fiziksel doğrulama YAPILMADI** (bu oturum donanıma erişemiyor): lidar
  port/model teyidi, kamera kalibrasyonu, servo fiziksel bağlantı yeri, RC6
  switch testi, ArUco marker'ın gerçek boyutta basımı. Yukarıdaki kontrol
  listesi bunlar için var.
