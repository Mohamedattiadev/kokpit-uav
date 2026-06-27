# 10 — YER İSTASYONU İZLEME (GCS + SIK Telemetry)

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `shared/protocol/packet_spec.md`
3. `Promptlar/07_mavlink_bridge.md`

## Görev
İki bağımsız izleme kanalı sağla:
1. **MAVLink GCS** (SIK Telemetry Radio V3, Pixhawk ↔ MissionPlanner/QGroundControl): standart MAVLink telemetri, yarışma direktör/jüri için
2. **Kokpit-özel UI** (LoRa TELEMETRY paketleri → yer istasyonu ESP32 TTGO ekranı + opsiyonel laptop dashboard): görev durumu, biyometrik onay, marker lock göstergeleri

## Açılışta Executor'a Sor (zorunlu)

1. **GCS yazılımı**: MissionPlanner (Windows, tavsiye — ArduPilot resmi) mı, QGroundControl (cross-platform) mu, ikisi de mi destekli olmalı?
2. **Laptop dashboard**: Gerekli mi? (Tavsiye: minimal, opsiyonel — yarışma esnasında çoğu şey ESP32 OLED'inden takip edilir)
3. **Eğer dashboard yapılacaksa**: Web UI (`fastapi` + `htmx`, tavsiye, basit) mı, native (`PyQt6`) mı, terminal (`textual`) mı?
4. **Veri kaynağı**: Dashboard MAVLink mi dinlesin (SIK), LoRa TELEMETRY mi (Kokpit ESP32 USB), her ikisi mi?
5. **Logging**: `.tlog` (ArduPilot standart, MissionPlanner replay) + JSONL Kokpit logları. Onay?
6. **Frekans**: Dashboard güncelleme 5 Hz yeterli. Onay?

## Mimari

```
gcs/
├── README.md                       # MissionPlanner kurulum + parametre yükleme
├── dashboard/                      # (opsiyonel) Python web UI
│   ├── pyproject.toml
│   ├── src/dashboard/
│   │   ├── main.py                 # FastAPI
│   │   ├── mavlink_listener.py
│   │   ├── lora_listener.py        # ESP32 USB serial
│   │   └── ws_broadcast.py
│   └── static/index.html
└── logs/                           # tlog + jsonl
```

## SIK Telemetry Setup

- SIK V3 ayarları: 57600 baud, NetID match (Pixhawk SiK <-> ground SiK), aynı `MAVLINK1/MAVLINK2`
- Pixhawk SERIAL1 protocol 2 (MAVLink 2), 57600
- Yarışma alanında 433 MHz LoRa ile interference: SIK 915 MHz (US) veya 433 MHz farklı channel/freq band test edilmeli; çakışırsa SIK 868/915 MHz tercih

## Kokpit Dashboard (opsiyonel ama tavsiye)

### Backend (`gcs/dashboard/src/dashboard/main.py`)
- FastAPI + WebSocket
- `mavlink_listener` MAVLink mesajları → state
- `lora_listener` ESP32 yer istasyonu USB serial → MISSION_STATUS, TELEMETRY paketleri parse
- WebSocket broadcast → frontend

### Frontend (`static/index.html`)
- Tek sayfa, htmx + tailwind cdn
- Paneller:
  - Drone konum (Leaflet harita, lat/lon trail)
  - Telemetri (alt, batt, GPS sat, mode)
  - Görev fazı (büyük renkli badge: IDLE/TAKEOFF/SEARCHING/...)
  - Marker lock / Face verified (yeşil/kırmızı LED)
  - Son LoRa paketi zaman damgası
  - Acil ABORT butonu (LoRa ABORT paketi → ESP32 → İHA)

## Kayıt
- Tüm MAVLink mesajları `.tlog` (mavutil `logfile_raw` parametresi)
- Tüm Kokpit event'leri `mission_YYYYMMDD.jsonl`
- Yarışma sonrası analiz için `scripts/plot_mission.py` (matplotlib)

## Testler
- `test_lora_listener.py`: bilinen TELEMETRY paketi → dashboard state
- `test_ws_broadcast.py`: state change → tüm bağlı clientlara push
- SITL: tam görev, dashboard'da harita üzerinde rota görünür
- HIL: SIK link + LoRa link aynı anda, interference yok

## Kabul Kriterleri
- SIK üzerinden MissionPlanner'da telemetri stabil, drop < %1
- Dashboard 5 Hz update, latency < 200 ms
- ABORT butonu → İHA RTL içinde 2 sn

## Verme
- MissionPlanner kurulum/param yükleme rehberi (`docs/gcs_setup.md`)
- (Opsiyonel) Dashboard çalışır FastAPI projesi
- Log analiz scriptleri
- README: SIK kanal config, LoRa-SIK interference notları
