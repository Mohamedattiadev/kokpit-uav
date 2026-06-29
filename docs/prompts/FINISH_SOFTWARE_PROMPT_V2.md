# FINISH_SOFTWARE_PROMPT_V2 — Yarışma Hazırlığı Final Sürüm

> **TEK ATIMLIK PROMPT.** Yeni bir Claude Code oturumunda yapıştır, sonra
> "execute" de. Claude 12 maddeyi sırayla bitirip push edecek. İnsan müdahalesi
> gerekmez (donanım hariç).
>
> **ÖNCEKİ DURUM:** M1–M12 tamam (commit `c98dd65`), 208 test geçer, CI yeşil.
> Bu prompt önceki çalışmanın üstüne 12 yeni özellik ekliyor.

---

## SEN KİMSİN

Kıdemli İHA + embedded + computer vision + MLOps + simülasyon + güvenlik
mühendisi. ArduCopter, PX4, Gazebo, ROS2, MAVLink, Jetson, TensorRT,
Flask, WebSocket, ESP32 konularında uzman. Güvenlik-kritik otonom sistem
deneyimi. Yarışma-grade production kod.

## NEREDEYIZ

Repo: `https://github.com/Mohamedattiadev/kokpit-uav`
Local: `cd /home/ati/Attia-Pro/Projectos/Teknofest-enes-group/kokpit-uav`
Branch: `main`

Mevcut:
- Sprint 0/1/2/3 + M1-M12 tamam
- 208 test geçer (`make test`, ~2 dk)
- CI yeşil
- `docs/DONANIM_PLANI.md` donanım ekibi için adım adım rehber
- Manual override iki yol: RC switch + LoRa MANUAL_REQUEST paketi
- PILOT_OVERRIDE abort_check RTL set etmez (pilot çakışması yok)

## ZORUNLU OKUMA

1. `docs/report/884462.pdf` — **CANONICAL SPEC. Yazılım bundan SAPAMAZ.**
   Her özelliği yazmadan önce rapor ilgili bölümünü oku. Raporla çelişen
   bir şey yapma. Raporla çelişen bir şeyi düzeltmen gerekiyorsa COMPLAINT
   olarak işaretle + commit etme, kullanıcıya sor.
2. `docs/PLAN.md` — Sprint dökümü
3. `docs/QUESTIONS_FOR_TEAM.md` — Karar geçmişi (Q1-Q7)
4. `docs/DONANIM_PLANI.md` — Donanım iş listesi
5. `docs/KILAVUZ.md` — Saha kılavuzu
6. `README.md`
7. `onboard/`, `tests/`, `simulation/`, `firmware/`, `tools/`, `scripts/`, `systemd/`

## NE YAPACAKSIN

12 madde sırayla. Her madde için:
1) Rapor uyumu doğrula (ilgili bölümü oku, ihlal eden değişiklik yapma)
2) Kod yaz → test yaz → `make test` yeşil tut → atomik commit → push
3) Bir sonrakine geç

**Rapor uyumu kuralları (tüm maddeler için):**
- Yüz tanıma: TensorRT primary, dlib fallback (Q6) ✓ değişmez
- Hassas iniş: PID primary + PRECLAND complement (Q7) ✓ değişmez
- LoRa: 433 MHz, AES-128 şifreli (rapor 2.1.3) ✓ değişmez
- ArUco: marker_length 0.30 m, target_id 0 (rapor + ardupilot/) ✓ değişmez
- Failsafe: batarya/GPS/link/geofence/crash (rapor 2.1.4) ✓ koruyarak genişlet
- Otonomi: Level 4 (rapor 1.2.2) — kullanıcı butonu sonrası tam otonom

---

### N1 — Preflight Check Script (EN YÜKSEK ÖNCELİK)

**Neden:** Arm öncesi tüm sistemler validate edilmeden uçuş izni verilmemeli.
Rapor 2.1.4 ve 3.3.2 "preflight kontroller" gerektiriyor.

**Dosya:** `tools/preflight_check.py`

**Kontroller:**
1. `CFG.validate()` — config tutarlılığı
2. ArduCopter param hash — beklenen vs. mevcut (`ardupilot/*.param` sha256)
3. Geofence aktif + polygon yüklü (`FENCE_ENABLE=1`, `FENCE_TOTAL>0`)
4. Lidar canlı veri (`telemetry().lidar_ok` + son 2 sn güncel)
5. Kamera FPS test (5 sn 25+ FPS olmalı)
6. LoRa link aktif (son 5 sn paket geldi mi)
7. GPS fix=3 + sat>=8 + hdop<=1.5
8. EKF status OK
9. Batarya voltaj > `battery_warn`
10. TRT engine veya dlib fallback hazır
11. `face_recognition` dataset 0'dan fazla yüz kayıtlı
12. systemd `kokpit-mc` running (gerçek donanımda)

**Çıktı:** Her kontrol PASS/FAIL + renkli tablo + JSON raporu
(`runs/preflight_<ts>.json`). FAIL varsa exit code 1.

**Entegrasyon:** `Mission.setup()` başında çağır, FAIL varsa
`RuntimeError("Preflight FAIL")` fırlat — arm denetlenmiş olur.

**Test:** mock telemetri ile her kontrol PASS/FAIL senaryosu (10+ test).

---

### N2 — Gazebo SITL + 6 Senaryo (P2.3 hâlâ açık)

**Neden:** PLAN.md P2.3 açık. Saha öncesi otonom davranışı 6 senaryoda
otomatik test edilmeli (rapor 3.3.2 "test stratejisi").

**Dosya yapısı:**
```
simulation/gazebo/
├── world/                      # Gazebo Garden .sdf dünyası
│   ├── kokpit_arena.sdf       # 200×200 m alan, ped, marker, alıcı
│   ├── models/marker_pad.sdf
│   └── models/recipient.sdf
├── scenarios/
│   ├── 01_happy_path.py
│   ├── 02_marker_lost.py
│   ├── 03_face_mismatch.py
│   ├── 04_link_lost.py
│   ├── 05_battery_low.py
│   └── 06_gps_lost.py
└── run_scenarios.sh            # tüm senaryoları sırayla
```

Her senaryo: SITL başlat → injecte fault → mission çalıştır → assert sonuç
(ör. happy: package_delivered=True; link_lost: RTL'e geçti vb.).

**CI entegrasyon:** Headless Gazebo (`gz sim -s --headless-rendering`).
Workflow'a `scenario-tests` job ekle (yalnız PR'larda, 10 dk timeout).
Gazebo yoksa skip.

**Test:** her senaryo bir pytest fonksiyonu (6 test).

---

### N3 — Mission Replay Dashboard

**Neden:** Görev sonrası analiz şu an manuel. Web tabanlı timeline + grafik
post-mortem hızlandırır (rapor 3.3.3 "log analizi").

**Dosya:** `scripts/replay_dashboard.py` (Flask, port 5000)

**Özellikler:**
- `runs/*/events.jsonl` listesi sol panelde
- Seçili görev → timeline (state geçişleri renkli bar)
- Altitude/battery/lidar grafik (matplotlib → PNG inline)
- ArUco offset trace + face confidence
- MAV mode geçişleri + failsafe olayları işaretle

**Bağımlılık:** Flask sadece. matplotlib zaten var.
**Erişim:** sadece `127.0.0.1:5000` bind (güvenlik).
**Test:** pytest+flask test_client ile route smoke (3 test).

---

### N4 — Telemetry Recorder (Forensic CSV)

**Neden:** Crash sebebi tespiti için her saniye state snapshot.
Rapor 3.3.3 "uçuş kaydı" gerektiriyor.

**Dosya:** `onboard/telemetry_recorder.py`

**Yaz:** her 1 Hz `runs/<ts>/telemetry.csv`:
```
ts_unix_us,lat,lon,alt_rel,vx,vy,vz,heading,roll,pitch,yaw,
battery_v,battery_pct,satellites,hdop,mode,armed,lidar_alt_body,
mission_state,failsafe_active
```

**Entegrasyon:** `Mission.setup()` başlatır, `close()` durdurur.
**Test:** 3 test — header doğru, satır yazıyor, close graceful.

---

### N5 — SysID Çakışma Koruma

**Neden:** Yarışmada 2+ takım yakın aralıkta uçabilir. MAVLink default
sysid=1 çakışması telemetri karışmasına yol açar.

**Değişiklik:**
- `LinkConfig` içine `target_sysid: int = 1` (env: `KOKPIT_SYSID`)
- `DroneController.connect()` heartbeat'te beklenen sysid değilse warn + retry
- ESP32 `packet_protocol.h` PKT_VERSION upgrade DEĞİL — sadece Jetson tarafı
- `tools/scan_sysid.py` MAVLink üzerinde aktif sysid'leri listele

**Test:** 4 test — env override, default, mismatch warn, scan output.

---

### N6 — Hava Durumu Pre-Check

**Neden:** Rüzgar > 5 m/s'de drone kontrolü zorlaşır. Kalkış öncesi
uyarı şart (rapor "saha emniyeti" 4.1).

**Dosya:** `tools/weather_check.py`

**API:** Open-Meteo (key gerekmez, ücretsiz):
```
GET https://api.open-meteo.com/v1/forecast?
    latitude={lat}&longitude={lon}&current=wind_speed_10m,
    precipitation,visibility
```

**Çıktı:** rüzgar/yağmur/görüş tablosu + GO/NO-GO karar.
- NO-GO: wind > 5 m/s, precipitation > 0.1 mm/h, visibility < 1000 m
- Preflight script'inden çağrılır

**Offline mode:** internet yoksa skip + uyarı.
**Test:** mock HTTP response 3 senaryo (calm/windy/rain).

---

### N7 — Auto-Tune Headless Orchestrator

**Neden:** Mission Planner saha laptop'unda her zaman yok. Headless tune
saha zamanı tasarrufu (rapor 4.3 "saha tuning").

**Dosya:** `tools/autotune.py`

**Akış:**
1. `set_mode("LOITER")` + arm gerekirse
2. AUTOTUNE param channel set (`AUTOTUNE_AXES=7`)
3. `set_mode("ALT_HOLD")` + pilot AUTOTUNE switch kontrol et
4. STATUSTEXT mesajlarını dinle ("AutoTune: success")
5. Bitince `MAV_CMD_DO_AUX_FUNCTION SAVE_AUTOTUNE` + Save param
6. `RTL` + disarm

**Manuel pilot kontrolü** ZORUNLU — script sadece orkestrasyon yapar,
pilot her zaman RC override edebilir.

**Test:** mock MAVLink ile state machine smoke (4 test).

---

### N8 — Live Camera Stream + ArUco Overlay (Jüri WOW Faktörü)

**Neden:** Yarışma jürisi otonomi seviyesini görsel olarak değerlendirir.
Canlı kamera + ArUco overlay + face confidence = ikna edici görsel.

**Dosya:** `onboard/dashboard_live.py` (Flask + MJPEG)

**Endpoint:**
- `GET /stream.mjpg` — canlı kamera feed (ArUco bbox + confidence overlay)
- `GET /status.json` — anlık telemetri JSON
- `GET /` — basit HTML, MJPEG + status polling

**Performans:** alt thread frame producer, lock'lu son frame paylaşımı.
**Erişim:** `0.0.0.0:8080` ama firewall whitelist sadece yarışma sahası IP'leri.
**Güvenlik notu:** prod'da basic auth gerekebilir (env `KOKPIT_DASH_PW`).
**Test:** pytest+flask, ArUco overlay frame oluşturma (3 test).

---

### N9 — Yedek Yer İstasyonu Hot Swap

**Neden:** Sahada ESP32 kırılırsa görev iptal olmamalı. İkinci ESP32
hazır hot swap.

**Değişiklik:**
- ESP32 boot sırasında MAC adresinden unique `station_id` türet
- `BOOT_BEACON` payload'una `station_id` ekle (uint32, MAC son 32 bit)
- Jetson `peer_station_id` track — değişirse log "GS hot-swap detected"
- Replay LRU zaten BOOT_BEACON'da clear oluyor (M10) — yeterli

**Dosya:** `firmware/esp32_ground_station/ground_station.ino` mods
**Test:** 3 test — boot_beacon payload + jetson decode + swap detect.

---

### N10 — Field Ops Quick Reference Card

**Neden:** Saha operatörü 30 sn'de hangi adım nerede olduğunu görmeli.
Tek sayfalık PDF/MD.

**Dosya:** `docs/SAHA_KART.md` (max 1 sayfa, A4 print uyumlu)

**İçerik:**
- Acil durum: pilot RC mode → STABILIZE; motor kill RC7 high
- Preflight komutu: `python3 tools/preflight_check.py`
- Görev başlat: `systemctl start kokpit-mc`
- Görev iptali: ESP32 butona uzun bas (ABORT) veya çift bas (MANUAL)
- Log: `runs/<ts>/`
- Telefon: takım irtibat numaraları (boş bırak, takım doldursun)

`make print-card` Makefile target ekle — markdown → PDF (pandoc varsa).

---

### N11 — Run Index + Otomatik Cleanup

**Neden:** `runs/` klasörü zamanla GB'lara büyür. Otomatik index +
eski log'ları sıkıştır.

**Dosya:** `scripts/runs_index.py`

**İşlev:**
- `runs/index.json` — her görev özet (ts, duration, package_delivered, abort_reason)
- 30 gün üzeri log'ları `runs/archive/<year>/<month>.tar.gz` sıkıştır
- Cron entry örnek (systemd timer) ekle

**Test:** 3 test — index build, archive trigger, old preserved.

---

### N12 — Final Integration Smoke

**Neden:** N1-N11 birlikte çalıştığını doğrula.

**Dosya:** `tests/test_final_integration.py`

**Senaryo:**
1. Preflight (mock telemetri OK) → PASS
2. Mission setup → recorder + dashboard başladı
3. Happy path simülasyon
4. Run sonrası index güncellendi + telemetry.csv var
5. Replay dashboard route 200

**Hedef:** 5+ test, en az 2 dk full run.

---

## ÇIKTI STANDARTLARI

- Python: type hint, ruff lint, docstring sadece "neden"
- Test: her madde 3+ yeni test, mevcut 208 test bozulmamalı
- Commit: atomik (N1, N2, ... başlık + neden body)
- **Co-Authored-By: Claude SATIRI KOYMA** (kullanıcı talebi)
- Her madde sonu push (`git push origin main`)
- CI yeşil tutmazsan dur, fix et

## KURAL — RAPOR UYUMU (TEKRAR)

- 884462.pdf canonical
- Her değişiklik raporla çelişmiyor mu? Çelişiyorsa COMPLAINT + commit etme
- Q1-Q7 kararları korunmalı
- Yeni bağımlılık eklerken `requirements.txt` + `requirements-ci.txt` güncel

## ÇALIŞTIRMA

```bash
cd /home/ati/Attia-Pro/Projectos/Teknofest-enes-group/kokpit-uav
source .venv/bin/activate
KOKPIT_SIM=1 python3 -m pytest tests/ --timeout=180 -q   # baseline 208 yeşil

# N1 → N12 sırayla:
# her madde:
KOKPIT_SIM=1 python3 -m pytest tests/ --timeout=180 -q   # hepsi geç
git add -A
git commit -m "feat(N#): kısa başlık ... (rapor uyumu)"
git push origin main

# Sonda:
gh run watch   # CI yeşil
```

## KABUL KRİTERLERİ (kendin doğrula)

- [ ] 208 + en az 36 yeni test (toplam ≥ 244) yeşil
- [ ] `make test` < 5 dk
- [ ] `make demo` yeşil
- [ ] N1-N12 her biri atomik commit + push
- [ ] CI workflow yeşil
- [ ] Hiçbir rapor taahhüdü ihlal yok
- [ ] `docs/PLAN.md` checkbox güncel (P2.3 tamam)
- [ ] `docs/QUESTIONS_FOR_TEAM.md` değişen karar yok

## RAPORLAMA

Bitince kullanıcıya:
- Üretilen dosya sayısı + satır sayısı
- Test sayısı + süre
- N1-N12 her birinin tek satır özeti
- Commit hash listesi
- En yüksek 3 risk + azaltma

---

**KURAL:** Kullanıcıya sormadan adım atlamak yok. Belirsizlikte rapor +
DONANIM_PLANI + AUDIT'ı kullan. Sessiz kalma. Progress event'leri stdout'a
basıyor ol. Bittiğinde özet ver.

**KURAL:** Co-Authored-By: Claude satırı KOYMA. Kullanıcı temizledi, böyle
kalsın.

**KURAL:** Donanım gerektiren bir test (gerçek Jetson, gerçek LoRa) için
graceful skip + stub yaz. API tam + test ile kanıtla.
