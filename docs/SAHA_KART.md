# KOKPIT SAHA KARTI (A4 print)

## ACİL DURUM
- **Pilot RC mode -> STABILIZE** (Jetson çekilir, M9 PILOT_OVERRIDE)
- **Motor kill: RC7 HIGH** (force disarm)
- **GS ABORT**: ESP32 butonu UZUN BAS
- **GS MANUAL**: ESP32 butonu ÇİFT BAS (Jetson LOITER'a alır)

## PREFLIGHT
```
cd ~/kokpit-uav && source .venv/bin/activate
python3 tools/preflight_check.py
```
12 kontrol PASS -> arm izni. Hava: `python3 tools/weather_check.py --lat ... --lon ...`

## GÖREV
- Başlat: `sudo systemctl start kokpit-mc`
- Durdur: `sudo systemctl stop kokpit-mc`
- Log: `runs/<ts>/`  (events.jsonl + telemetry.csv)
- Replay: `python3 scripts/replay_dashboard.py` -> http://127.0.0.1:5000
- Canlı kamera: http://<jetson>:8080  (KOKPIT_DASH_PW set ile auth)

## FAILSAFE EŞIKLERI
- Batarya LOW 22.0 V (RTL), CRT 21.0 V (LAND)
- GPS sats>=8, hdop<=1.5, fix=3
- Geofence radius 150 m, max alt 30 m
- Link timeout 5 s

## KRİTİK ENV
- `KOKPIT_SIM=0` (gerçek donanım)
- `KOKPIT_SYSID=1` (çakışma varsa değiştir, tools/scan_sysid.py ile kontrol)
- `KOKPIT_PREFLIGHT=1` (sim'de zorla)
- `KOKPIT_RECORD=1` (sim'de telemetry CSV)

## İRTİBAT
Pilot: __________________
Teknik: __________________
Tıbbi: __________________
