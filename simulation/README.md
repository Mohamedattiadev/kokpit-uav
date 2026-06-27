# simulation/ — Simülasyon ve Test

Üç katmanlı test stratejisi (drone düşmeden önce her şey burada yakalanır):

## 1. Yazılım demosu (kurulum gerektirmez) — `software_demo.py`

ArduPilot, Pixhawk, kamera, LoRa **hiçbiri gerekmez**. `FakeDrone` fiziği +
sentetik ArUco kamerası ile tüm görev akışını çalıştırır. GERÇEK ArUco tespiti
ve GERÇEK görsel servo PID kullanılır.

```bash
KOKPIT_SIM=1 python3 software_demo.py              # başarılı teslimat
KOKPIT_SIM=1 python3 software_demo.py --reject     # biyometrik ret -> dönüş
KOKPIT_SIM=1 python3 software_demo.py --save-video # logs/demo.mp4 üretir
```

## 2. Otomatik testler — `../tests/`

Birim + entegrasyon testleri (CRC, PID, durum makinesi, ArUco, uçtan uca görev):

```bash
KOKPIT_SIM=1 python3 -m pytest ../tests/ -q
```

## 3. Gerçek ArduPilot SITL — `run_sitl.sh` + `test_mission_sitl.py`

MAVLink komutları GERÇEK ArduCopter fizik motoruna gider (en gerçekçi test).
Görüş ve LoRa hâlâ simüle edilir.

**Terminal 1** — SITL'i başlat:
```bash
./run_sitl.sh
```

**Terminal 2** — görevi SITL'e karşı çalıştır:
```bash
KOKPIT_SIM=1 python3 test_mission_sitl.py
```

### ArduPilot SITL kurulumu (bir kez)
```bash
git clone --recurse-submodules https://github.com/ArduPilot/ardupilot
cd ardupilot
Tools/environment_install/install-prereqs-ubuntu.sh -y
. ~/.profile
export PATH=$PATH:$HOME/ardupilot/Tools/autotest
```
Ayrıntı: https://ardupilot.org/dev/docs/sitl-simulator-software-in-the-loop.html

## Bağlantı

Görev yazılımı SITL'e `udp:127.0.0.1:14551` üzerinden bağlanır
(`onboard/config.py` → `LinkConfig.mavlink_sim`). `run_sitl.sh` bu çıkışı
`--out=udp:127.0.0.1:14551` ile açar.

## Önemli not

Bu simülasyon katmanları **uçuş öncesi** mantık doğrulaması içindir; gerçek
uçuştan önce mutlaka:
1. SITL'de tam görevi çalıştır,
2. Pervanesiz/bağlı (tethered) donanım testleri yap,
3. Geniş, boş ve güvenli bir sahada ilk uçuşu dene (bkz. ana README güvenlik
   kontrol listesi).
