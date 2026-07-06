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
>
> **Kolaylık:** İŞ-1, İŞ-2, İŞ-3 (paket testi) ve İŞ-4 (param yükleme)
> için artık **tek komutla çalışan scriptler** var (`scripts/` ve
> `tools/` klasörlerinde) — Mission Planner'da tıklaya tıklaya dosya
> yüklemek veya elle paket saymak yerine tek satır komut çalıştırıp
> soruları cevaplaman yeterli. Her bölümde en üstte bu komut var; script
> bir sebeple çalışmazsa hemen altında "elle yapılış" yedek yöntemi de
> duruyor. Fiziksel hareket gerektiren şeyler (drone'u 6 pozisyonda
> tutmak, döndürmek, uçurmak, Arduino IDE'den USB ile firmware yüklemek)
> doğası gereği otomatikleştirilemez — o kısımlar hâlâ elle yapılıyor.
> Scriptlerin kendisi de çalışırken bunu ekrana hatırlatır (hangi kısmı
> kendisi yaptığını, hangi kısmın hâlâ senin elinle yapılması gerektiğini
> söyler).
>
> **Hangisi otomatik, hangisi elle — kısa özet:**
>
> | Script | Ne otomatikleşti | Hâlâ elle/fiziksel olan |
> |---|---|---|
> | `is1_jetson_kurulum.sh` | Her şey — bu işin fiziksel tarafı yok | — |
> | `is2_extrinsics_kalibrasyon.sh` | Değerleri dosyaya yazma + doğrulama | Şerit metreyle ölçmek |
> | `lora_paket_testi.py` | Paket sayma + kayıp hesabı | Kabloyu takmak, butona basmak |
> | `param_yukle.py` | 7 dosyayı yükleme + reboot | Kalibrasyon/uçuş (drone'u elle döndürmek/uçurmak) |

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

### Tek komutla otomatik kurulum (önerilen)

Jetson'a bağlan (klavye+monitör ile veya SSH ile uzaktan), terminali aç ve
tek bu satırı yapıştır:

```bash
bash ~/Teknofest/scripts/is1_jetson_kurulum.sh
```

Bu script sırayla:
1. Jetson'ı tam güç moduna alır (`nvpmodel -m 0` + `jetson_clocks`)
2. Repo'nun bulunduğu gerçek klasörü **kendisi otomatik bulur** ve
   `systemd/kokpit-mc.service` dosyasındaki iki yolu (WorkingDirectory +
   ExecStart) buna göre kendisi doldurur — elle dosya açıp düzenlemene
   gerek yok
3. Servisi kurar, "her açılışta otomatik başlat" olarak işaretler, hemen
   başlatır
4. Çalıştığını kendisi kontrol eder ve son logları ekrana basar

Script sırasında sadece **iki şey** senden istenir: başlamadan önce
Enter'a basman, ve `sudo` şifreni girmen (ekranda görünmez, normal — yazıp
Enter'a bas). Script biterken "İŞ-1 TAMAM" yazarsa her şey yolunda demektir.

Canlı logları izlemek istersen (script bittikten sonra, istersen):
```bash
journalctl -u kokpit-mc -f
```
(Durdurmak için Ctrl+C.) `WATCHDOG=1` yazan satırlar ve LoRa paket logları
görüyorsan her şey yolunda demektir.

<details>
<summary>Script çalışmazsa — elle yapılış (yedek yöntem)</summary>

### Adım 1 — Jetson'ı tam güç moduna al

```bash
sudo nvpmodel -m 0        # Jetson'ı "MAXN" (tam güç) moduna geçirir
sudo jetson_clocks        # işlemci/GPU hızını sabit en yükseğe kilitler
nvpmodel -q                # kontrol: ekrana "MAXN" veya "15W" yazmalı
```

### Adım 2 — Görev yazılımının otomatik başlamasını sağla

`systemd/kokpit-mc.service` dosyasında **iki tane** yol var, ikisini de
kendi repo yoluna göre düzelt (bu Jetson'da repo `~/Teknofest`'te, örnek):

```
WorkingDirectory=/home/jetson/Teknofest
ExecStart=/home/jetson/Teknofest/.venv/bin/python3 -m onboard.mission
```

**İkisini de** değiştir — sadece `WorkingDirectory`'yi değiştirip
`ExecStart`'ı unutmak servisin hata vermesine sebep olur (`python3: No
module named 'pymavlink'` gibi), çünkü `ExecStart` mutlaka
`.venv/bin/python3`'ü göstermeli — sistemin genel `python3`'ünde
(`/usr/bin/python3`) proje kütüphaneleri (pymavlink, opencv, numpy...)
kurulu değil. Kendi Jetson'ında repo başka bir klasördeyse (örneğin
`/home/kokpit/kokpit-uav`), yukarıdaki iki satırı o gerçek yolla değiştir.

```bash
sudo cp ~/Teknofest/systemd/kokpit-mc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kokpit-mc
```

### Adım 3 — Çalıştığını kontrol et

```bash
systemctl status kokpit-mc
journalctl -u kokpit-mc -f
```
</details>

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

### Adım 4 — Ölçtüğün değerleri yazılıma gir (tek komut, otomatik doğrulamalı)

Jetson'da terminal aç ve tek bu satırı çalıştır:

```bash
bash ~/Teknofest/scripts/is2_extrinsics_kalibrasyon.sh
```

Bu script sana sırayla 12 soru soracak: önce `CAM x`, `CAM y`, `CAM z`,
`CAM roll deg`, `CAM pitch deg`, `CAM yaw deg`, sonra aynı sırayla
`LIDAR x`, `LIDAR y`, `LIDAR z`, `LIDAR roll deg`, `LIDAR pitch deg`,
`LIDAR yaw deg`. Her soruda köşeli parantez içinde bir **varsayılan değer**
gösterilir (örn. `CAM x (ileri) [0.0]:`) — yukarıda kağıda yazdığın ölçüyü
gir; kamera/lidar hiç eğik değilse (çoğu montajda böyledir) `roll/pitch/yaw`
sorularında hiçbir şey yazmadan sadece Enter'a basarak varsayılanı (`0.0`)
kabul edebilirsin. Değerleri metre cinsinden, nokta kullanarak gir (virgül
değil — örn. `0.10`).

Tüm sorular bitince script **kendisi otomatik olarak** şunları da yapar:
- Girdiğin değerleri `onboard/configs/extrinsics.yaml` dosyasına kalıcı
  olarak yazar
- Doğrulama testlerini çalıştırır ve sonucu ekrana basar
- En sonda yazdığın tüm değerleri özet olarak gösterir

Ekranda **"İŞ-2 TAMAM — tüm testler PASSED"** yazısını görürsen bu iş
bitmiştir, başka bir şey yapmana gerek yok.

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

### Adım 2 — Gerçek LoRa üzerinden paket testi (tek komut, otomatik sayar)

Elle "kaç paket ulaştı" saymak yerine, Jetson'da terminal aç ve tek bu
satırı çalıştır (LoRa alıcısı Jetson'a USB/UART ile bağlıyken):

```bash
~/Teknofest/.venv/bin/python3 ~/Teknofest/tools/lora_paket_testi.py
```

Script sana bağlı portu seçtirir (bulduğu portları numaralı liste olarak
gösterir, genelde `1` yeterli), sonra "Basmayı bitirince Enter'a bas"
der — sen yer istasyonundaki butona istediğin kadar bas (öneri: 100 kere),
bitirince terminale dönüp Enter'a bas. Script ulaşan paket sayısını, kayıp
sayısını ve kayıp yüzdesini **kendisi hesaplayıp** ekrana basar; ayrıca
kayıp %30'un üzerindeyse veya hiç paket gelmediyse ne kontrol etmen
gerektiğini de Türkçe olarak söyler (anten, kanal/adres ayarı, GPS fix vb.).

- Hedef: kayıp neredeyse sıfır olmalı (kablosuz olduğu için sıfır'a çok
  yakın kayıp normaldir).

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

### Adım 1 — Ayar (parametre) dosyalarını yükle (tek komut, otomatik)

Mission Planner'da 7 dosyayı tek tek "Load from file" + "Write Params" ile
yüklemek yerine, Pixhawk'ı Jetson'a USB veya TELEM kablosuyla bağlayıp tek
bu komutu çalıştırabilirsin:

```bash
~/Teknofest/.venv/bin/python3 ~/Teknofest/tools/param_yukle.py
```

Script sırayla:
1. Bulduğu bağlantı portlarını numaralı liste olarak gösterir (USB mi
   TELEM mi bağlı olduğunu sorar, sonra port seçtirir)
2. Pixhawk'a MAVLink üzerinden bağlanır
3. `ardupilot/` klasöründeki 7 dosyayı **doğru sırada, kendisi** yükler:
   `kokpit_baseline.param` (frame/motor/EKF3) → `kokpit_companion.param`
   (Jetson bağlantısı) → `kokpit_failsafe.param` (batarya/link/RC/GPS) →
   `kokpit_geofence.param` (alan sınırı) → `kokpit_lidar.param` (mesafe
   sensörü) → `kokpit_precland.param` (hassas iniş) → `kokpit_servo.param`
   (paket bırakma servosu)
4. Sonunda "Pixhawk'ı yeniden başlatayım mı?" diye sorar — Enter'a basman
   yeterli, gerekli reboot'u kendisi yapar

Bu 7 dosya bu Jetson'da gerçek bir ArduCopter SITL'ine karşı bizzat test
edilip doğrulanmıştır (7/7 başarıyla yüklendi).

**Not — geofence polygon ayrı yüklenir:** `kokpit_geofence.param` sadece
sınır özelliğini açar (`FENCE_ENABLE`, `FENCE_ACTION=RTL` vb.); yarışma
alanının **gerçek köşe noktaları** (`kokpit_arena.poly`) sahaya özel
olduğu için repoda henüz yok — sahada GPS ile alanın köşelerini gezip
Mission Planner'ın **Flight Plan → Polygon** aracıyla ayrıca çizip
Pixhawk'a yüklemen gerekiyor (bu kısım GPS ile sahada gezmeyi gerektirdiği
için otomatikleştirilemez).

<details>
<summary>Script çalışmazsa — Mission Planner ile elle yükleme (yedek yöntem)</summary>

Mission Planner programını aç, Pixhawk'a bağlan. **CONFIG → Full
Parameter Tree** kısmına git ve 7 dosyayı yukarıdaki sırayla, birini
bitirip diğerine geçerek yükle. **Her dosyayı yükledikten sonra mutlaka
"Write Params" butonuna bas** ve Pixhawk'ı yeniden başlat (reboot) — aksi
halde ayar kalıcı olarak kaydolmaz. Dosya adları `ardupilot/README.md`'de
de aynı şekilde listelidir.
</details>

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
hissediliyorsa: Mission Planner'da Extended Tuning ekranından **RC7 DIŞINDA
boş bir kumanda koluna** (örneğin RC6) AUTOTUNE atarsın, LOITER modunda
kalkış yapıp o kolu açarsın, drone 5-10 dakika kendi kendine ince ayar
yapar, bitince LAND yapıp ayarları kaydedersin (Save Params).
**RC7'yi kullanma** — o kanal aşağıdaki "Acil Durum Kuralları" bölümünde
MOTOR KILL anahtarı olarak ayrılmıştır; aynı kola iki farklı fonksiyon
atarsan acil durumda motoru kilitlemek yerine yanlışlıkla autotune
tetiklenebilir.

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
| Servo paketi bırakmıyor | Servo ayarı yanlış | `SERVO9_FUNCTION=0`, `SERVO9_MIN=1000`, `SERVO9_MAX=2000` parametrelerini kontrol et (bkz. `ardupilot/kokpit_servo.param`) |

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
- [ ] Rüzgar 5 m/s'nin altında, yağmur yok — `~/Teknofest/.venv/bin/python3 ~/Teknofest/tools/weather_check.py --lat <enlem> --lon <boylam>` ile kontrol edilebilir (`--lat`/`--lon` zorunlu, uçuş alanının gerçek koordinatlarını yaz)
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

| İş | Kod durumu | Kalan iş | Tek komut | Kim |
|---|---|---|---|---|
| İŞ-1 TensorRT | ✅ Bitti | `bash ~/Teknofest/scripts/is1_jetson_kurulum.sh` (~15 dk) | ✅ tam otomatik | Sistem sorumlusu |
| İŞ-2 Extrinsics | — (kod gerekmiyor) | Ölçüm (fiziksel, 1-2 saat) + `bash ~/Teknofest/scripts/is2_extrinsics_kalibrasyon.sh` | ✅ girişten sonra otomatik | Mekanik + elektronik |
| İŞ-3 ESP32 | ✅ Bitti | Karta yükleme (Arduino IDE, elle) + `~/Teknofest/.venv/bin/python3 ~/Teknofest/tools/lora_paket_testi.py` (paket sayımı otomatik) | Yarı otomatik | Elektronik/firmware |
| İŞ-4 Uçuş testleri | — (kod gerekmiyor) | `~/Teknofest/.venv/bin/python3 ~/Teknofest/tools/param_yukle.py` (otomatik) + kalibrasyon/uçuş (fiziksel, elle) | Yarı otomatik | Zeki Emir + takım |

Daha fazla detay, tüm komutlar ve genişletilmiş sorun giderme tabloları:
[`docs/DONANIM_PLANI.md`](DONANIM_PLANI.md).
