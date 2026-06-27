# 06 — SENSÖR FÜZYONU (Lidar + Kamera + EKF Cross-Check)

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `Promptlar/05_aruco_visual_servoing.md` (ArUco z tahmini)
3. `Promptlar/07_mavlink_bridge.md` (Pixhawk EKF'e veri besleme)

## Görev
Benewake TFS20 lidar verisini Jetson tarafında okuyup:
1. Pixhawk'a `DISTANCE_SENSOR` MAVLink mesajı olarak besle (ArduCopter EKF3 buna güveniyor — irtifa füzyonu, terrain follow).
2. ArUco poz tahmininin Z bileşeniyle cross-check yap, sapma > %20 ise marker tespitine düşük güven ver.
3. Barometric drift'i kompanze et (alçak irtifada lidar mutlak referans).

## Açılışta Executor'a Sor (zorunlu)

1. **Lidar bağlantısı**: Jetson'a doğrudan UART (`/dev/ttyTHS2`) (tavsiye — daha az gecikme, Pixhawk'a Jetson MAVLink ile basıyor) mi, Pixhawk'a doğrudan (ArduCopter param ile) mı?
2. **Update rate**: TFS20 100 Hz default. Jetson 50 Hz throttle (tavsiye, MAVLink hat trafiği) yeterli mi?
3. **Outlier rejection**: Median filter window=5 (tavsiye) mi, Kalman filter mi?
4. **Min/max range tuning**: TFS20 0.1–30 m. Yarışma için 0.1–15 m clamp yeterli mi?
5. **ArUco-Lidar fusion strategy**: Weighted average (lidar 0.7, aruco 0.3, tavsiye) mi, hard switch (alçakta sadece lidar) mı?

## Mimari

```
jetson/mission_computer/src/kokpit/sensor_fusion.py
jetson/mission_computer/src/kokpit/lidar.py
```

## Lidar Sürücüsü

TFS20 binary protokolü:
```
[0x59, 0x59, DIST_L, DIST_H, STRENGTH_L, STRENGTH_H, TEMP_L, TEMP_H, CKSUM]
```

```python
async def lidar_loop(state, mav):
    reader = await open_serial(cfg.lidar.port, cfg.lidar.baud)
    median_buf = collections.deque(maxlen=5)
    while True:
        frame = await read_tfs20_frame(reader)
        if frame.strength < 100 or frame.distance_cm > 1500:
            continue  # düşük güven
        median_buf.append(frame.distance_cm)
        dist_m = statistics.median(median_buf) / 100.0
        state.lidar_alt = dist_m
        await mav.send_distance_sensor(
            min_distance_cm=10, max_distance_cm=1500,
            current_distance_cm=int(dist_m * 100),
            orientation=MAV_SENSOR_ROTATION_PITCH_270,  # downward
            covariance=2,
        )
```

## Cross-Check

```python
def fuse_altitude(lidar_m: float, aruco_z_m: float) -> tuple[float, float]:
    """Return (fused_alt, confidence 0-1)."""
    if aruco_z_m is None:
        return lidar_m, 1.0
    diff = abs(lidar_m - aruco_z_m)
    rel = diff / max(lidar_m, 0.1)
    if rel > 0.2:
        return lidar_m, 0.5  # mismatch → marker uzaklığına şüphe
    return 0.7 * lidar_m + 0.3 * aruco_z_m, 1.0
```

`state.altitude_confidence` aruco_servoing kullanır.

## ArduCopter Tarafı Param Önerileri
ArduCopter'da:
- `RNGFND1_TYPE = 10` (MAVLink)
- `RNGFND1_ORIENT = 25` (down)
- `RNGFND1_MIN_CM = 10`, `RNGFND1_MAX_CM = 1500`
- `EK3_RNG_USE_HGT = 70` (alçak irtifada lidar mutlak)
- `EK3_SRC1_POSZ = 2` (rangefinder)

Bu paramlar `docs/ardupilot_params.md`'e yazılsın.

## Testler
- `test_tfs20_parser.py`: bilinen byte stream → doğru distance
- `test_median.py`: outlier injection → filtre tutuyor mu
- `test_fusion.py`: lidar=2m, aruco=2.1m → fused~2.03m
- `test_fusion.py`: lidar=2m, aruco=5m → confidence düşük
- HIL: gerçek lidar + MAVLink, ArduCopter `RANGEFINDER` mesajı receive

## Kabul Kriterleri
- Lidar 50 Hz, jitter < 5 ms
- ArduCopter EKF3 rangefinder use'da, alçakta hover stable (drift < 5 cm/sn)
- Lidar dropout (kapalı/uzak) → graceful fallback baroya

## GÜÇLENDİRMELER (AUDIT)

### G1. Extrinsics Yaml (KRİTİK — sessiz sapma kaynağı)
`configs/extrinsics.yaml` ortak modül 05 ile:
```yaml
lidar_to_body:  { x: 0.03, y: 0.0, z: -0.12 }   # body frame'de lidar
cam_to_body:    { x: 0.05, y: 0.0, z: -0.10, roll: 0, pitch: 0, yaw: 0 }
```
Lidar reading body-Z'ye projeksiyon yapılırken offset uygula. Aksi takdirde kamera-lidar Z 5–10 cm farklı, fusion yanlış.

### G2. Time Sync (lidar timestamp)
Her lidar sample'a `ts_unix_us` (modül 03 G2 ile aynı zaman tabanı). MAVLink DISTANCE_SENSOR `time_boot_ms` doldur.

### G3. Health Monitor
Lidar dropout > 1 sn → `state.lidar_healthy=False` → pre-arm check fails, fusion barometre'ye fallback.

## Verme
- Çalışan `lidar.py` + `sensor_fusion.py`
- `docs/ardupilot_params.md` (lidar + EKF3 paramları, MissionPlanner ile yüklenecek `.param` dosyası dahil)
- README: kablo şeması, Pixhawk SR4 vs Jetson UART karar gerekçesi
