# FINISH_SOFTWARE_PROMPT — Kalan Yazılım İşini Bitir

> **TEK ATIMLIK PROMPT.** Bu dosyayı yeni bir Claude Code oturumunda yapıştır, sonra "execute" de. Claude tüm açıkları kapatacak ve push edecek. İnsan müdahalesi gerekmez (donanım hariç).

---

## SEN KİMSİN

Sen kıdemli bir İHA + embedded + computer vision + MLOps yazılım mühendisisin. ArduCopter, PX4, ROS2, MAVLink, Jetson, TensorRT, OpenCV, LoRa, ESP32 (Arduino + ESP-IDF + mbedTLS) konularında uzmansın. Güvenlik-kritik otonom sistem geliştirme deneyimin var. Yarışma-grade production kod üretirsin.

## NEREDEYIZ

Repo: `https://github.com/Mohamedattiadev/kokpit-uav` (sahip: Mohamedattiadev)
Local: `cd /home/ati/Attia-Pro/Projectos/Teknofest-enes-group/kokpit-uav`

Mevcut durum:
- Sprint 0 (bug fix) — TAMAM
- Sprint 1 (uçuş güvenliği) — TAMAM (crash det, failsafe priority, servo guards, lidar subscribe, geofence, RC priority)
- Sprint 2 (rapor uyumu) — KISMEN (LoRa AES + chunked face image TAMAM; **TRT face backend YOK**)
- 150 test geçiyor (`make test`)
- README, PLAN, QUESTIONS, KILAVUZ hazır
- 7 ArduCopter param dosyası hazır (`ardupilot/*.param`)

## ZORUNLU OKUMA (önce yap)

1. `docs/report/884462.pdf` — **CANONICAL SPEC**. Yazılım bundan sapamaz. Sapacaksan komplaint et + commit etme.
2. `docs/PLAN.md` — Sprint dökümü
3. `docs/QUESTIONS_FOR_TEAM.md` — Verilen kararlar (özellikle Q6 = TRT, Q7 = hibrit PRECLAND+PID)
4. `docs/prompts/AUDIT_GUCLENDIRMELER.md` — Audit bulguları
5. `onboard/`, `firmware/esp32_ground_station/`, `simulation/`, `tests/`, `ardupilot/` ağacı

## NE YAPACAKSIN

Aşağıdaki 12 maddeyi sırayla bitir. Her madde için: kod yaz → test yaz → `make test` yeşil tut → commit (atomik, açıklayıcı) → sonraki maddeye geç. Sonda push.

### M1 — TensorRT Face Backend (rapor şart, Sprint 2 P1.3)
**Neden:** Rapor 2.1.2 + 3.3.1.2 "TensorRT destekli CNN" diyor; mevcut dlib CPU only.
- `tools/build_face_trt.py`: ONNX → TRT engine build script. ArcFace R50 (`buffalo_l`) + RetinaFace MobileNet 0.25 (InsightFace modelleri). Engine cache key: `{model}_{trt_version}_{jetpack}_{precision}.engine`. Jetson olmadığında graceful skip.
- `onboard/face_verifier.py` `TRTBackend` class ekle: detector + embedder + 5-point align + cosine similarity. Engine path env `KOKPIT_TRT_DIR` veya `onboard/models/`. `tensorrt` import yoksa graceful fallback'i koru.
- `FaceVerifier.__init__` force_backend="trt" → TRT zorla.
- Engine yoksa → dlib fallback, log uyarı.
- Test: TRT mevcutsa engine load smoke test; yoksa skip.

### M2 — Extrinsics Transform (Sprint 3 P2.6)
**Neden:** Kamera/lidar mount offset göz ardı → sessiz pose hatası 5-10 cm.
- `onboard/configs/extrinsics.yaml`: `cam_to_body: {x, y, z, roll, pitch, yaw}`, `lidar_to_body: {x, y, z}` default değerleri (tahmini ZD550 frame için).
- `onboard/extrinsics.py`: `load_extrinsics()`, `transform_cam_to_body(tvec_cam) -> tvec_body`, `transform_lidar_to_body(z_lidar) -> z_body`.
- `onboard/aruco_detector.py` veya `visual_servo.py`: pose tahmininden sonra `transform_cam_to_body` uygula.
- `onboard/mavlink_interface.py` RANGEFINDER handler: lidar Z'yi extrinsics ile düzelt (`state.lidar_alt_body`).
- `tools/calibrate_extrinsics.py`: interaktif rehber (kullanıcıdan cetvelle ölçü iste, yaml'a yaz).
- Test: identity extrinsics → tvec değişmemeli; offset ile beklenen body değer.

### M3 — Time Sync (Sprint 3 P2.1)
**Neden:** ESP32/Jetson/Pixhawk farklı saatler; log korelasyonu imkânsız.
- `onboard/time_sync.py`: arka plan thread, MAVLink `SYSTEM_TIME` dinle, monoton tabanlı offset hesabı (root yetkisi olmadan `time.time()` farkı; gerçek slew için `adjtimex` opsiyonel). `get_synced_unix_us()` API.
- ESP32 `ground_station.ino`: NMEA `$GNRMC` UTC alındığında `settimeofday()` veya yazılım RTC (manuel epoch counter).
- Tüm yeni log satırları `ts_unix_us` field'ı içermeli. `mission.py`, `visual_servo.py`, `lora_receiver.py` print yerine `log.info(..., ts=...)` (structlog opsiyonel ama eklemeden de OK — sadece f-string'lere `ts=` ekle).
- Test: `time_sync.get_synced_unix_us()` mock MAVLink dispatch ile doğru offset hesaplıyor mu.

### M4 — Watchdog + systemd (Sprint 3 P2.5)
**Neden:** Jetson çökerse otomatik restart yok.
- `systemd/kokpit-mc.service`: `Restart=on-failure RestartSec=3 WatchdogSec=15 NotifyAccess=main Type=notify ExecStart=/usr/bin/python3 -m kokpit.main`
- `onboard/main.py` veya `mission.py` ana loop: `sdnotify` paketi ile her 5 sn `WATCHDOG=1`. `sdnotify` yoksa graceful skip.
- README'ye install adımları ekle: `sudo cp systemd/kokpit-mc.service /etc/systemd/system/ && sudo systemctl enable kokpit-mc && sudo systemctl start kokpit-mc`
- Test: import sdnotify mock; notify çağrısı yapılıyor mu.

### M5 — Log Download Otomasyonu (Sprint 3 P2.4)
**Neden:** Post-mortem analiz için Pixhawk dataflash log'u Jetson'a çekilmiyor.
- `onboard/log_downloader.py`: `download_latest_log(mav, output_dir)` → MAVLink `LOG_REQUEST_LIST` → en yeni log'u `LOG_REQUEST_DATA` ile çek → `runs/YYYYMMDD_HHMMSS/dataflash.bin`.
- `mission.py` görev sonunda (DISARM sonrası) çağır.
- `scripts/plot_mission.py`: dataflash.bin + jsonl → matplotlib plot (irtifa, batarya, hata).
- Test: mock MAVLink ile log_list dispatch + data chunk simülasyonu.

### M6 — Yaw Alignment Delivery'de (Sprint 2 P1.5)
**Neden:** Alıcı drone'a değil, drone alıcıya bakmalı.
- `onboard/visual_servo.py`: APPROACHING sonunda (lock + irtifa OK) ArUco marker rotation'dan ped yön referansı al. `cv2.Rodrigues(rvec)` → yaw extract.
- `mavlink_interface.py`: `condition_yaw(heading_deg, relative=False)` API ekle (`MAV_CMD_CONDITION_YAW`).
- `mission.py` `_do_biometric_verify` öncesi `drone.condition_yaw(marker_yaw_deg)`.
- Test: rvec → yaw extraction sanity.

### M7 — LoRa RSSI Telemetri (Sprint 3 P2.7)
**Neden:** Link kalitesi izlenmiyor; yarışma sahasında sinyal düştüğünde fark edilmez.
- ESP32 `ground_station.ino`: LoRa E32 transparent mode'da RSSI register direkt yok; alternatif: `setLoraMode(true)` config moduna alıp `0xC1 0xC1 0xC1` komutuyla son paket RSSI oku. Veya UART command `0xC3 0xC3 0xC3` (`AUX` toggle gerekir). Karmaşıksa **`packet_loss_pct`** alanını ESP32 tarafında tahmini (ACK yok) → Jetson hesaplıyor: 1 sn pencerede beklenen vs alınan paket sayısı.
- `onboard/lora_receiver.py`: `rx_rate_hz`, `last_rssi`, `packet_loss_pct` istatistikleri.
- `onboard/telemetry_tx.py` (yeni): Jetson 1 Hz TELEMETRY paketi (mode, batt, mission_phase, rssi) → LoRa → ESP32 ekranda göster.
- ESP32: gelen TELEMETRY paketini decode + TFT'de göster.
- Test: SimLoRaReceiver paket sayım istatistiği doğru.

### M8 — Reboot Recovery (Sprint 3 P2.8)
**Neden:** Jetson mid-mission reboot → state IDLE, ama Pixhawk RTL'de olabilir; çakışma riski.
- `onboard/mission.py` `setup()`: bağlandıktan sonra `mav.telemetry().mode` oku. AUTO/GUIDED/RTL/LAND aktifse + armed ise → `MissionState.READ_ONLY` yeni state'e geç. Bu state'te Jetson sadece telemetri okur, hiç komut göndermez. Pilot manual'a alana kadar.
- `state_machine.py` `MissionState.READ_ONLY` ekle, VALID_TRANSITIONS'a yaz.
- Test: setup before run, mode=GUIDED+armed → state=READ_ONLY.

### M9 — PILOT_OVERRIDE Faz
**Neden:** Pilot kumandayı alırsa (Manual/Stabilize'a geçerse) Jetson devre dışı kalmalı.
- `_failsafe_loop` içine: mode "MANUAL" veya "STABILIZE" veya "ACRO" ise → `_push_failsafe(PRIO_USER_ABORT, "PILOT_OVERRIDE", ...)`.
- Aksiyonu: hiç komut gönderme, read-only kal. Pilot tekrar GUIDED'a alırsa IDLE'a dön.
- Test: mode değişimi → failsafe queue içeriği doğru.

### M10 — BOOT_BEACON Recovery (Eksik tamamla)
**Neden:** ESP32 reboot olunca Jetson'ın replay LRU'sundaki seq'ler invalid olur; yeni seq başlangıcı kullanılmalı.
- `lora_receiver.py` `_handle_packet`: BOOT_BEACON geldiğinde `parser._seen_set.clear()` + `parser._seen_seqs.clear()` + log "peer reboot detected, replay window reset".
- Test: BOOT_BEACON sonrası eski seq tekrar kabul edilmeli.

### M11 — CI Doğrulama
**Neden:** `.github/workflows/ci.yml` mevcut ama test edilmedi.
- Workflow'u koş (`gh workflow run ci.yml` veya push tetiklesin). dlib derlemesi ubuntu-22.04'te 5+ dk; opsiyonel olarak `requirements-ci.txt` üret (face_recognition hariç, opencv-python-headless), CI'da bunu kullan.
- `make test` CI'da yeşil olmalı.
- Workflow başarısız ise düzelt.

### M12 — Spiral Search Düzgün Arşimet
**Neden:** Mevcut quarter-turn jumps optimum değil; marker arama süresi uzun.
- `visual_servo.py` `spiral_search`: gerçek Arşimet eğrisi `r(t) = a + b*t, θ(t) = ω*t`. Sürekli velocity komut akışı (10 Hz), kesik kesik goto_global değil.
- Tolerans + timeout aynı kalsın (`marker_search_timeout_s`).
- Test: trajektori geometrik doğrulama.

---

## ÇIKTI STANDARTLARI

- **Python:** type hint, ruff lint, docstring yalnız "neden", asyncio veya threading idiomatic
- **C/C++:** clang-format, `-Wall -Werror`
- **Test:** her madde için en az 2 yeni test, mevcut 150 test bozulmamalı
- **Commit:** her madde için atomik commit (M1, M2, ... başlığı + "neden" body)
- **Hiçbir maddeyi atlatma.** Donanım gerektiren stub yapılabilir ama API tam + test ile kanıtlanmalı.

## KURAL — RAPOR UYUMU

- Rapor 884462.pdf canonical. Her değişiklik raporla çelişmiyor mu kontrol et.
- Q1: yüz JPEG transfer (legacy recipient_id korunsun) ✓
- Q2: AES-128-CCM + persistent seq + SHA ✓ (zaten yapıldı)
- Q6: TensorRT face primary, dlib fallback (M1)
- Q7: PID primary + PRECLAND complement (zaten yapıldı + M2 transform pekiştirir)
- LoRa 433 MHz ✓
- Visual Servoing PID Loop ✓

## ÇALIŞTIRMA SIRASI

```bash
cd /home/ati/Attia-Pro/Projectos/Teknofest-enes-group/kokpit-uav
source .venv/bin/activate  # yoksa: python3 -m venv .venv + pip install pytest pytest-timeout opencv-python-headless numpy pymavlink cryptography
KOKPIT_SIM=1 python3 -m pytest tests/ --timeout=180 -q  # baseline yeşil mi doğrula
```

Sonra M1'den M12'ye sırayla:
```bash
# her madde sonu:
KOKPIT_SIM=1 python3 -m pytest tests/ --timeout=180 -q  # hepsi geçmeli
git add -A
git commit -m "feat(MN): kısa başlık ... (rapor uyumu)"
```

Sonda:
```bash
git push origin main
gh run watch    # CI yeşil mi izle
```

## KABUL KRİTERLERİ (kendin doğrula)

- [ ] 150 + en az 24 yeni test (toplam ≥ 174) yeşil
- [ ] `make test` < 4 dk
- [ ] `make demo` halen yeşil
- [ ] M1-M12 hepsi commit'lendi
- [ ] CI workflow yeşil (GitHub Actions)
- [ ] Hiçbir rapor taahhüdü ihlal yok
- [ ] `docs/PLAN.md` checkbox güncel
- [ ] `docs/QUESTIONS_FOR_TEAM.md` Q6 (TRT) durumu "TAMAM" işaretli

## RAPORLAMA (bitince kullanıcıya)

- Üretilen dosya sayısı, satır sayısı
- Test sayısı / süre
- M1-M12 her birinin tek satır özeti
- Commit hash listesi
- Bilinen TODO (gerçek Jetson hardware bekleyen)
- Risk değerlendirmesi (en yüksek 3 risk + azaltma önerisi)

---

**KURAL:** Hiçbir adımı kullanıcıya sormadan atla. Belirsizlikte AUDIT_GUCLENDIRMELER.md + raporu kullan. Sessiz kalma. Progress event'leri stdout'a basıyor ol. Bittiğinde özet ver.
