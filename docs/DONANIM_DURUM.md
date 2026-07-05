# Donanım Durumu — Kalan İşler (Ekip İçin Detaylı Anlatım)

> Bu dosya `docs/DONANIM_PLANI.md`'nin (600+ satırlık ana plan) sadeleştirilmiş
> ve **daha çok açıklamalı** hâli. Amaç: hiç bilmeyen biri bile bu dosyayı
> okuyup adım adım ne yapması gerektiğini anlayabilsin. Bir terim/komut
> anlaşılmazsa `docs/DONANIM_PLANI.md`'de aynı başlığın altında daha fazla
> detay + sorun giderme tablosu var.
>
> **Yazılım tarafı tamamen bitti** (369 test yeşil, CI yeşil). Yani
> aşağıdaki 4 işin hiçbirinde artık kod yazmaya gerek yok — hepsi elle,
> fiziksel olarak yapılacak işler (kablo bağlama, ölçüm alma, ekranda bir
> yere tıklama, drone'u uçurma gibi).

---

## Önce birkaç kelimeyi açıklayalım

Aşağıda sık geçen ve kafa karıştırabilecek terimler var. Baştan okuyup
geçmen, sonraki bölümleri anlamanı kolaylaştırır.

- **Jetson** — dronun üzerindeki küçük bilgisayar (NVIDIA marka). Kamera
  görüntüsünü işleyen, yüz tanıyan, görev mantığını çalıştıran şey budur.
  Telefonunun/laptopunun küçük ve dronun üzerine monte edilmiş hâli gibi
  düşün.
- **Pixhawk** — dronun "uçuş beyni". Motorları döndüren, GPS'i okuyan,
  dengeyi sağlayan asıl donanım. Jetson ona komut gönderir ("şuraya git",
  "in"), ama Pixhawk gerçek uçuşu yönetir.
- **ArduCopter** — Pixhawk'ın içinde çalışan işletim sistemi/yazılım
  (drone'un "beyninin yazılımı").
- **Mission Planner** — Windows bilgisayarına kurulan, Pixhawk'a USB/telemetri
  ile bağlanıp ayar yapmanı, kalibrasyon yapmanı, harita üzerinde uçuş
  planlamanı sağlayan program. Drone'la konuşmanın ana yolu budur.
- **Param (parametre) dosyası** — Pixhawk'a yüklenen, "motor sayısı kaç",
  "batarya kaç voltta uyarsın", "hangi alan sınırı" gibi yüzlerce ayarı
  içeren bir metin dosyası. Elle tek tek girmek yerine dosya olarak toplu
  yüklenir.
- **Kalibrasyon** — sensörlere "sıfır noktan burası" demek. Örneğin pusula
  (compass) kalibrasyonu yapılmazsa drone kuzeyi yanlış bilir ve daire
  çizerek uçar (aşağıda "toilet bowl" diye geçen sorun budur).
- **LoRa** — yer istasyonu (buton olan kutu) ile drone arasında haberleşmeyi
  sağlayan uzun menzilli kablosuz radyo modülü. WiFi değil, çok daha uzun
  mesafe (km) ama az veri taşır.
- **ESP32** — yer istasyonundaki (butonlu kutu) küçük mikrodenetleyici.
  Arduino'ya benzer, LoRa modülünü ve ekranı o yönetir.
- **Extrinsics / offset** — kameranın ve lidarın (mesafe sensörü) dronun tam
  merkezine göre nerede durduğunun ölçüsü (santimetre/metre cinsinden).
  Bu ölçü yazılıma girilmezse, "kamera şurayı görüyor" bilgisi yanlış
  yorumlanır ve iniş birkaç santim kayar.
- **Failsafe** — bir şey ters giderse (batarya azaldı, sinyal kesildi gibi)
  drone'un otomatik olarak güvenli bir şey yapmasıdır (eve dönme, olduğu
  yere inme gibi).
- **RTL (Return To Launch)** — "kalktığın yere otomatik geri dön" modu.
- **Systemd servisi** — Jetson açıldığında, kullanıcı hiçbir şey yapmadan,
  görev yazılımının otomatik başlamasını sağlayan arka plan mekanizması.
  "Bilgisayar açılınca bu program kendiliğinden çalışsın" demenin yoludur.

---

## Genel Sıra — Hangisini Ne Zaman Yapmalıyız?

```
İŞ-1 (Jetson/TensorRT)  ─┐
                         ├─ paralel yapılabilir, birbirini beklemez
İŞ-3 (ESP32 firmware)   ─┘

İŞ-2 (kamera/lidar ölçümü)  →  İŞ-2 bitmeden İŞ-4'e (uçuş testi) GEÇME.
                                Kalibrasyon yapılmadan otonom iniş testi
                                yaparsan drone hedefi 5-10 cm yanlış görür.

İŞ-4 (param + test uçuşları)  →  EN SON yapılacak iş. İŞ-1, İŞ-2, İŞ-3
                                   bitmeden başlama — hepsi İŞ-4'ün
                                   önkoşulu.
```

Yani mantıklı sıra: **önce İŞ-1 ve İŞ-3'ü aynı anda/paralel bitir → sonra
İŞ-2 (kalibrasyon) → en son İŞ-4 (gerçek uçuş testleri).**

---

## İŞ-1 — Jetson'da TensorRT'i Aktif Etme

**Şu an durum:** Yazılım (kod) tarafı tamamen bitti ve gerçek bir Jetson
üzerinde çalıştığı doğrulandı. Geriye sadece **iki tane komut çalıştırmak**
kaldı — kod yazmıyorsun, sadece terminale birkaç satır yazıyorsun.

**Kim yapmalı:** Jetson'a fiziksel erişimi ve `sudo` şifresi olan biri
(donanım/sistem sorumlusu — genelde takımın Jetson'ı kuran kişisi).

**Ne kadar sürer:** ~15 dakika.

**Neden gerekli, basitçe:** Jetson, pil tasarrufu için varsayılan olarak
"yavaş" modda çalışır (az güç harcar ama yüz tanıma da yavaş olur — saniyede
1-2 kare). Bunu "tam güç" moduna almazsak yüz tanıma yarışma sırasında çok
yavaş kalır. İkinci adım da, Jetson her yeniden başladığında görev
yazılımının **kendiliğinden** çalışmasını sağlıyor — yoksa her seferinde
elle başlatman gerekir.

### Adım 1 — Jetson'ı tam güç moduna al

Jetson'a bağlan (klavye+monitör ile veya SSH ile uzaktan), terminali aç ve
şu üç satırı **sırayla** yapıştır, her birinden sonra Enter'a bas:

```bash
sudo nvpmodel -m 0        # Jetson'ı "MAXN" (tam güç) moduna geçirir
sudo jetson_clocks        # işlemci/GPU hızını sabit en yükseğe kilitler
nvpmodel -q                # kontrol: ekrana "MAXN" veya "15W" yazmalı
```

`sudo` yazınca şifre soracak — Jetson'ın kullanıcı şifresini gir (ekranda
görünmez, normal, yazıp Enter'a bas).

### Adım 2 — Görev yazılımının otomatik başlamasını sağla

Önce şu dosyayı aç ve içindeki bir satırı kontrol et:
`systemd/kokpit-mc.service`. İçinde `WorkingDirectory=/opt/kokpit-uav`
diye bir satır var — eğer repo Jetson'da farklı bir klasördeyse (örneğin
`/home/kokpit/kokpit-uav`), bu satırı o gerçek yolla değiştir.

Sonra terminalde (kendi repo yolunu `<repo-yolu>` yerine yaz):

```bash
cd <repo-yolu>
sudo cp systemd/kokpit-mc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kokpit-mc
```

Bu dört satır sırasıyla: servis dosyasını sisteme kopyalar → sistemin yeni
servisi tanımasını sağlar → servisi "her açılışta otomatik başlat" olarak
işaretler → hemen şimdi başlatır.

### Adım 3 — Çalıştığını kontrol et

```bash
journalctl -u kokpit-mc -f
```

Bu komut, servisin canlı loglarını ekrana akıtır (durdurmak için Ctrl+C).
`WATCHDOG=1` yazan satırlar ve LoRa paket logları görüyorsan her şey
yolunda demektir.

### Bitti mi, kontrol listesi:

- [ ] `nvpmodel -q` çalıştırınca "MAXN" veya "15W" yazıyor
- [ ] `systemctl status kokpit-mc` yazınca "active (running)" görünüyor

Daha fazla sorun giderme (örn. `sdkmanager` Jetson'ı görmüyor, TensorRT
import hatası vb.) için: `docs/DONANIM_PLANI.md` → **İŞ-1** bölümü,
"Sorun Giderme" tablosu.

---

## İŞ-2 — Kamera ve Lidar'ın Yerini Ölçüp Yazılıma Bildirme

**Şu an durum:** Bu iş **hiç başlanmadı** — yazılımda bir eksiklik yok,
sadece elle bir ölçüm işi hiç yapılmamış.

**Kim yapmalı:** Mekanik ekip (drone gövdesini yapan) + elektronik ekip
(kamera/lidar'ı takan) birlikte — ölçüm iki kişiyle daha kolay (biri tutar,
biri ölçer).

**Ne kadar sürer:** 1-2 saat. Kamera veya lidar'ın yeri sonradan değişirse
(örneğin başka bir yere monte edilirse) bu iş tekrar yapılmalı.

**Önkoşul:** Drone gövdesi bitmiş olmalı, kamera ve lidar (mesafe sensörü)
üzerine gerçekten vidalanmış/yapıştırılmış olmalı — henüz takılmadıysa
önce onu bitirin.

### Neden bu iş yapılmadan uçmamalıyız?

Drone, hedefin tam üstüne inerken kamerayla "işaret (marker) şurada"
diyor. Ama kamera dronun tam ortasında değil — genelde birkaç santim
önde/altında duruyor. Yazılıma "kamera dronun merkezinden şu kadar
uzakta" demezsek, yazılım kamerayı merkez sanır ve iniş noktası 5-10 santim
kayar. Yarışma raporunun hedefi ±14 cm hassasiyet — bu ölçüm yapılmadan
o hassasiyeti tutturmak neredeyse imkansız.

### Gerekli malzemeler

- Şerit metre (santimetre okuyabilen, 2 metre yeterli)
- Su terazisi (dronun düz durduğunu kontrol etmek için)
- İsteğe bağlı: dijital açıölçü (kamera/lidar hafif eğik monteliyse)
- Kağıt kalem (ölçüleri not almak için)

### Adım 1 — Drone'u düz bir yere koy

Su terazisini dronun üstüne koy, tamamen yatay olduğundan emin ol (hafif
eğikse ölçüler yanlış çıkar). Dronun burnunun (ön tarafının) hangi yöne
baktığını sabitle — örneğin odadaki bir kapıya baksın, referans olarak
kullanacağız.

### Adım 2 — Kamera'nın merkeze göre yerini ölç

Referans nokta: **Pixhawk'ın (uçuş kontrolcüsü kutusunun) tam altı**. Oradan
kamera lensinin merkezine kadar üç yönde ölçüm alacaksın:

| Ölçülecek değer | Nasıl ölçülür | Örnek |
|---|---|---|
| `cam.x` (ileri-geri) | Pixhawk'tan kameraya, **burun yönünde (ileri)** kaç metre? Kamera önde ise pozitif (+) yaz. | `0.00` (tam altındaysa) |
| `cam.y` (sağ-sol) | Kamera sağa kaymışsa pozitif (+), sola kaymışsa negatif (−) | `0.00` |
| `cam.z` (yukarı-aşağı) | Kamera Pixhawk'tan ne kadar **aşağıda**? Aşağıda olduğu için hep pozitif (+) yaz. | `0.10` (10 cm aşağıda) |
| `cam.roll/pitch/yaw` | Kamera tam aşağı bakıyorsa üçü de `0`. Hafif eğik monteliyse açıölçüyle derece ölç. | `0, 0, 0` |

**Önemli:** Tüm değerleri **metre** cinsinden yazacaksın (santimetreyi
100'e böl — örneğin 10 cm = `0.10`).

### Adım 3 — Lidar'ın (mesafe sensörünün) yerini aynı şekilde ölç

Aynı mantık, bu sefer lidar'ın ışın çıkış noktasına göre:

| Ölçülecek değer | Nasıl ölçülür |
|---|---|
| `lidar.x` | Pixhawk'tan lidar'a ileri yönde mesafe (m) |
| `lidar.y` | Sağa/sola kayma (m) |
| `lidar.z` | Lidar'ın aşağı mesafesi (m) |

### Adım 4 — Ölçtüğün değerleri yazılıma gir

Jetson'da terminal aç:

```bash
cd <repo-yolu>
source .venv/bin/activate
python3 tools/calibrate_extrinsics.py
```

Bu programı çalıştırınca sana sırayla `CAM x`, `CAM y`, `CAM z` ve
`LIDAR x`, `LIDAR y`, `LIDAR z` diye soracak — yukarıda kağıda yazdığın
değerleri (metre cinsinden, nokta kullanarak, virgül değil — örn. `0.10`)
sırasıyla gir ve Enter'a bas. Program bitince
`onboard/configs/extrinsics.yaml` adında bir dosya oluşturacak; bu dosya
girdiğin ölçüleri kalıcı olarak saklar.

### Adım 5 — Doğru girildiğini kontrol et

```bash
cat onboard/configs/extrinsics.yaml
```

Ekrana az önce girdiğin sayıları görmelisin. Sonra:

```bash
KOKPIT_SIM=1 pytest tests/test_extrinsics.py -v
```

Bu komut, dosyanın doğru okunup okunmadığını otomatik kontrol eder — hepsi
"PASSED" (geçti) yazmalı.

### Bitti mi, kontrol listesi:

- [ ] Drone su terazisiyle düz durumdayken ölçüldü
- [ ] Tüm değerler metre cinsinden girildi (santimetre değil!)
- [ ] `onboard/configs/extrinsics.yaml` dosyası oluştu
- [ ] Yukarıdaki test komutu hepsi PASSED verdi
- [ ] (İŞ-4 uçuş testlerinde) marker üzerine iniş hatası ±14 cm içinde

### Sık yapılan hatalar

- Negatif değer yazarken eksi işaretini unutmak (`-0.05` yazman gerekirken
  `0.05` yazmak) — sonuç ters yönde kayar.
- Virgül kullanmak (`0,10`) — programın anlaması için **nokta** olmalı
  (`0.10`).
- Ölçümü rüzgarlı/eğik bir yerde yapmak — mutlaka düz, sabit bir zeminde
  yap.
- Lidar sürekli `0` metre okuyorsa bu kalibrasyon sorunu değil, lidar'ın
  Pixhawk'a bağlantı ayarı (`RNGFND1_TYPE` parametresi) sorunu — İŞ-4'teki
  param yükleme adımına bak.

---

## İŞ-3 — ESP32 Yer İstasyonuna Firmware Yükleme + Saha Testi

**Şu an durum:** Kod tarafı tamamen bitti (bilgisayarda derlenip test
edildi, 7/7 test geçti). Geriye **gerçek ESP32 kartına yükleme** ve
**gerçek radyo testi** kaldı — bunlar bir bilgisayardan yapılamaz, elde
kart olması gerekiyor.

**Kim yapmalı:** Elektronik/firmware ekibi (ESP32 kartıyla, LoRa modülüyle
uğraşan kişiler).

**Ne kadar sürer:** Yarım gün.

### Adım 1 — Firmware'i ESP32 kartına yükle

Bilgisayarına Arduino IDE (veya PlatformIO) kurulu olmalı. Gerekli
kütüphanelerin listesi `firmware/esp32_ground_station/README.md`
dosyasında yazıyor — önce onları kur. Sonra ESP32 kartını USB kabloyla
bilgisayara bağla, Arduino IDE'de doğru kartı/portu seç, ve
`firmware/esp32_ground_station/ground_station.ino` dosyasını aç →
"Upload" (yükle) butonuna bas.

### Adım 2 — Gerçek LoRa üzerinden 100 paketlik test

Jetson tarafında görev yazılımını çalıştır (veya sadece LoRa gönderici
kısmını test moduna al), yer istasyonundaki butona 100 kere bas (veya
otomatik test paketleri gönder) ve kaç tanesinin karşıya ulaştığını say.

- Hedef: kayıp neredeyse sıfır olmalı (kablosuz olduğu için sıfır'a çok
  yakın kayıp normaldir).
- Sürekli %30'dan fazla paket kaybediyorsa: anten bağlantısını kontrol et,
  mesafeyi azalt, ya da aradaki engelleri (metal, duvar) kaldır. (Zaten
  sinyal kötüyse ekrandaki buzzer otomatik uyarı verecek — bunu da bu
  testte duyup duymadığını kontrol et.)

### Adım 3 — Ekranın okunabilirliğini kontrol et

TFT ekranda üç satır bilgi görünmeli: mod+batarya, görev fazı, sinyal
gücü+kayıp oranı. Bunu güneş ışığında/gölgede farklı açılardan bakarak
okunabilir olduğundan emin ol — saha koşullarında ekran parlaması sorun
olabilir.

### Bitti mi, kontrol listesi:

- [ ] Firmware gerçek karta yüklendi, kart açılıp çalışıyor
- [ ] 100 paketlik loopback testi yapıldı, kayıp oranı kabul edilebilir
- [ ] TFT ekran gerçek ışıkta okunabiliyor

---

## İŞ-4 — Parametre Yükleme ve Gerçek Uçuş Testleri

**Şu an durum:** Hiç başlanmadı. Bu, en uzun ve en dikkat gerektiren iş —
çünkü sonunda drone gerçekten havalanıyor.

**Kim yapmalı:** Uçuş kontrolcüsü (Zeki Emir) + yanında en az bir kişi daha
(gözlemci/güvenlik).

**Ne kadar sürer:** Yaklaşık 2 gün (yarım gün ayar yükleme, 1.5 gün kademeli
uçuş testleri).

**Önkoşul — bunlar bitmeden BAŞLAMA:** İŞ-1, İŞ-2, İŞ-3 tamamlanmış olmalı;
drone'un montajı tam bitmiş olmalı; batarya dolu olmalı.

### Adım 1 — Ayar (parametre) dosyalarını yükle

Mission Planner programını aç, Pixhawk'a bağlan. Üstteki menüden
**CONFIG → Full Parameter Tree** kısmına git. Repo içindeki `ardupilot/`
klasöründe 7 tane hazır ayar dosyası var — bunları **sırasıyla**, birini
bitirip diğerine geçerek yükle:

```
1. 01_initial_setup.param       → drone tipini, motor sayısını ayarlar
2. 02_radio_calibration.param   → kumandanın min/max değerlerini ayarlar
3. 03_battery_failsafe.param    → batarya azalınca ne olacağını ayarlar
4. 04_geofence.param            → yarışma alanının sınırını ayarlar
5. 05_compass_calibration.param → pusula ayarları
6. 06_lidar_rangefinder.param   → mesafe sensörü ayarları
7. 07_precland.param            → hassas iniş ayarları
```

**Her dosyayı yükledikten sonra mutlaka "Write Params" butonuna bas** ve
Pixhawk'ı yeniden başlat (reboot) — aksi halde ayar kalıcı olarak
kaydolmaz.

### Adım 2 — Kalibrasyon turu (uçmadan önce zorunlu)

Mission Planner'da sırasıyla:

1. **Accelerometer (ivmeölçer) kalibrasyonu** — Initial Setup → Accel
   sekmesi, ekrandaki talimatları izleyerek drone'u 6 farklı pozisyonda
   (düz, ters, sağa yatık, sola yatık, burnu yukarı, burnu aşağı) tutuyorsun.
2. **Pusula (compass) kalibrasyonu** — drone'u elinle her yöne, 8 farklı
   şekilde döndürüyorsun (ekran seni yönlendirir).
3. **Radio (kumanda) kalibrasyonu** — tüm kumanda kollarını uç noktalarına
   kadar hareket ettiriyorsun, min/max değerler kaydoluyor.
4. **ESC kalibrasyonu** — motorların hepsinin aynı anda, aynı hızda
   başladığından emin olmak için.
5. **Lidar testi** — Mission Planner'ın Status ekranında, drone'u elinle
   yukarı-aşağı kaldırıp indirdikçe mesafe değerinin değiştiğini kontrol
   et.
6. **Geofence (sınır) testi** — drone'u MANUAL modda elinle sınırın
   kenarına yaklaştır (uçurmadan, elde tutarak simüle edebilirsin veya
   çok kısa mesafede test edebilirsin), RTL'in (eve dönüş) tetiklendiğini
   gör.

### Adım 3 — Kademeli uçuş testleri (açık, güvenli bir alanda)

**ÇOK ÖNEMLİ KURAL: Bir adımda bir şey yanlış giderse veya garip
davranırsa DUR. Sebebini bulup çözmeden bir sonraki adıma GEÇME.**
Otonom uçuşa atlamadan önce her kademeyi tek tek doğrulamak, drone'un
düşmesini önler.

```
1) MANUAL modda hover     — pilot kumandayla ~1 metre yükseklikte,
                             30 saniye havada tutuyor. Sallanıyor mu,
                             bir tarafa kayıyor mu diye izle.

2) STABILIZE modda hover   — aynı test ama bu modda drone kendi kendine
                             dengede kalmaya çalışır (otomatik leveling).
                             Bu çalışıyor mu kontrol et.

3) LOITER modda hover      — GPS'e göre sabit durma modu. 1 dakika havada
                             tut, 1 metreden fazla kaymaması lazım.

4) RTL testi               — LOITER'dayken kumandadan RTL moduna geç,
                             drone'un otomatik olarak kalkış noktasına
                             dönüp inmesini izle.

5) GUIDED (yönlendirilmiş) waypoint — Mission Planner'ın haritasında
                             50 metre ileride bir nokta işaretle, GUIDED
                             moduna al, drone'un oraya gidip geri
                             gelmesini izle.

6) Tam otonom görev        — artık yazılımı çalıştırıyoruz:
                             KOKPIT_SIM=0 python3 -m onboard.mission
                             (veya Jetson'daki systemd servisi zaten
                             otomatik çalışıyor). Yer istasyonundaki
                             butona bas, tüm görev akışının (kalkış →
                             gidiş → hassas iniş → yüz tanıma → paket
                             bırakma → eve dönüş) uçtan uca çalıştığını
                             izle.
```

### Adım 4 — Gerekirse PID ayarı (Auto-Tune)

Eğer 3. adımdaki testlerde drone titriyor, sallanıyor veya kontrolü gevşek
hissediliyorsa: Mission Planner'da Extended Tuning ekranından bir kumanda
koluna (genelde RC7) AUTOTUNE atarsın, LOITER modunda kalkış yapıp o
kolu açarsın, drone 5-10 dakika kendi kendine ince ayar yapar, bitince
LAND yapıp ayarları kaydedersin (Save Params).

### Bitti mi, kontrol listesi:

- [ ] 7 ayar dosyası da yüklendi ve "Write Params" yapıldı
- [ ] İvmeölçer + pusula + kumanda + ESC kalibrasyonları tamamlandı
- [ ] Lidar canlı veri veriyor (Mission Planner'da değer değişiyor)
- [ ] Sınıra yaklaşınca RTL gerçekten tetikleniyor
- [ ] Adım 1'den 5'e kadar hepsi sorunsuz tamamlandı
- [ ] Tam otonom görev 5 kere art arda denendi ve başarılı oldu
- [ ] Marker üzerine iniş hatası ortalama 20 cm'nin altında

### Sık karşılaşılan sorunlar

| Sorun | Muhtemel sebep | Ne yapmalı |
|---|---|---|
| Drone dairesel sallanarak uçuyor ("toilet bowl") | Pusula kalibrasyonu düzgün yapılmamış | Kalibrasyonu metal eşyalardan (masa, alet çantası) uzakta tekrar yap |
| GPS sinyali bulamıyor | Anten yanlış yerde | GPS anteniyle RC/telemetri antenini farklı kollara ayır |
| LOITER modunda sürükleniyor | GPS sinyali zayıf (yüksek HDOP) | GPS sinyali güçlenene kadar bekle, gerekirse EKF'yi sıfırla |
| Otonom kalkış başlamıyor | Pre-arm (kalkış öncesi) kontrol hatası | Mission Planner'daki "STATUSTEXT" mesaj kutusunu oku, hangi kontrolün başarısız olduğu orada yazar |
| Servo paketi bırakmıyor | Servo ayarı yanlış | `SERVO9_FUNCTION=0`, `SERVO9_MIN=1100`, `SERVO9_MAX=1900` parametrelerini kontrol et |

---

## Acil Durum Kuralları (Uçuş Sırasında — Ezberle)

```
Pilot HER ZAMAN elindeki kumandayla anında kontrolü geri alabilir.

1) Drone beklenmedik bir şey yaparsa  → kumandadan STABILIZE moduna geç
2) Hâlâ kontrol edilemiyorsa          → MOTOR KILL anahtarına bas (RC7 yukarı)
3) Drone yere düştüyse                → HEMEN pil bağlantısını çıkar (yangın riski)
```

---

## Saha Testi / Yarışma Öncesi Son Kontrol (her uçuştan önce yapılır)

- [ ] Batarya tam şarjlı (6S paket için 24V'un üzerinde) + yedek batarya yanında hazır
- [ ] Manual, Stabilize, Loiter, Guided modlarının hepsi test edildi
- [ ] Geofence (alan sınırı) yüklü ve aktif
- [ ] Telemetri bağlantısı ve RC (kumanda) bağlantısı kontrol edildi
- [ ] Rüzgar 5 m/s'nin altında, yağmur yok (`tools/weather_check.py` ile kontrol edilebilir)
- [ ] Drone'un 100 metre çevresinde izleyici/başka insan yok
- [ ] Yangın söndürücü elinizin altında
- [ ] Pilot lisanslı/sertifikalı ve dinlenmiş (yorgun pilot uçurmasın)

---

## Bir Şey Ters Giderse Kime Söylemeli?

- **Yazılımda bir hata görürsen** (görev yazılımı çökme, beklenmedik davranış):
  önce `journalctl -u kokpit-mc -n 200` komutuyla son logları oku, sonra
  GitHub Issues'a yaz veya doğrudan Arda / Attia'ya haber ver.
- **Donanımda bir hata görürsen** (motor, Pixhawk, kablo sorunu):
  Mission Planner'ın "Messages" sekmesinden hata mesajını oku, uçuş sonrası
  otomatik inen dataflash log'unu kaydet, Zeki Emir'e ilet.

---

## Özet Tablo — Şu An Ne Kaldı?

| İş | Kod durumu | Kalan iş | Kim |
|---|---|---|---|
| İŞ-1 TensorRT | ✅ Bitti | 2 terminal komutu (~15 dk) | Sistem sorumlusu |
| İŞ-2 Extrinsics | — (kod gerekmiyor) | Ölçüm + kalibrasyon aracı çalıştırma (1-2 saat) | Mekanik + elektronik |
| İŞ-3 ESP32 | ✅ Bitti | Karta yükleme + saha radyo testi (yarım gün) | Elektronik/firmware |
| İŞ-4 Uçuş testleri | — (kod gerekmiyor) | Param yükleme + kademeli test uçuşları (2 gün) | Zeki Emir + takım |

Daha fazla detay, tüm komutlar ve genişletilmiş sorun giderme tabloları:
[`docs/DONANIM_PLANI.md`](DONANIM_PLANI.md).
