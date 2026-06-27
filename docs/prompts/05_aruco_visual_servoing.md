# 05 — ARUCO TESPİT + VISUAL SERVOING PID

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `Promptlar/03_jetson_mission_computer.md`
3. `Promptlar/06_sensor_fusion.md` (lidar irtifa, paralel geliştirilebilir)
4. `Promptlar/07_mavlink_bridge.md` (pozisyon komut API'si)

## Görev
IMX219 alt kamerasından gelen frame'lerde ArUco marker'ı tespit et, kameranın marker'a göre relatif pozunu hesapla, bir PID döngüsüyle Pixhawk'a `SET_POSITION_TARGET_LOCAL_NED` mesajları göndererek İHA'yı marker merkezine ±5 cm hassasiyetle yaklaştır. Marker kaybolursa sarmal arama (spiral search) tetikle.

## Açılışta Executor'a Sor (zorunlu)

1. **ArUco sözlüğü**: `DICT_4X4_50` (tavsiye — küçük, hızlı tespit) mi, `DICT_5X5_100` mu, `DICT_APRILTAG_36h11` (daha robust ama büyük) mı?
2. **Marker boyutu**: Ped üzerindeki marker'ın fiziksel kenar uzunluğu kaç cm? (Pozisyon hesabı için zorunlu, varsayım: 20 cm)
3. **Kamera kalibrasyonu**: Hazır `camera_matrix.yaml` var mı, yoksa chessboard ile kalibrasyon scripti de yazılsın mı?
4. **Kontrol frekansı**: 20 Hz (tavsiye — Pixhawk EKF rate ile uyumlu) mi, 30 Hz mi?
5. **Koordinat sistemi**: `MAV_FRAME_BODY_OFFSET_NED` (tavsiye — relatif hareket, basit) mi, `LOCAL_NED` (mutlak, EKF origin gerekir) mi?
6. **PID kazançları için başlangıç**: `Kp=0.5, Ki=0.0, Kd=0.1` X/Y için, Z için `Kp=0.3, Ki=0.05, Kd=0.05`. Onay? *(Saha testinde tune edilecek)*
7. **Çoklu marker fallback**: Ped üzerinde iç içe nested marker (büyük + küçük) kullanılacak mı? Yüksekte büyük, alçakta küçük tespit edilir — bu mimari tercih mi?

## Mimari

```
jetson/mission_computer/src/kokpit/aruco_servoing.py
jetson/mission_computer/configs/
├── camera_intrinsics.yaml
└── pid_gains.yaml
jetson/mission_computer/scripts/
├── calibrate_camera.py        # chessboard 9x6
└── tune_pid.py                # log replay tool
```

## Fonksiyonel Akış

### 1. Kamera Stream
- OpenCV `cv2.VideoCapture(GST_PIPELINE)` — Jetson CSI için GStreamer:
  ```
  nvarguscamerasrc ! video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1
  ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! appsink
  ```
- Async wrapper: `asyncio.to_thread` ile `cap.read()`

### 2. Marker Tespit
```python
detector = cv2.aruco.ArucoDetector(
    cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
    cv2.aruco.DetectorParameters(),
)
corners, ids, _ = detector.detectMarkers(gray)
```

### 3. Poz Tahmini
```python
rvec, tvec, _ = cv2.aruco.estimatePoseSingleMarkers(
    corners, marker_size_m, camera_matrix, dist_coeffs)
# tvec = [x, y, z] kamera frame'inde, metre
```
- Kamera → body frame transform (kamera nadir bakıyor: roll=0, pitch=0, yaw=0 varsayılır; ofset hesaba katılırsa daha iyi)
- Lidar mesafesini z ile cross-check (modül 06)

### 4. PID Döngüsü
```python
class PID:
    def __init__(self, kp, ki, kd, i_max=1.0):
        ...
    def __call__(self, error: float, dt: float) -> float:
        ...

pid_x = PID(**cfg.pid_xy)
pid_y = PID(**cfg.pid_xy)
pid_z = PID(**cfg.pid_z)

async def servoing_loop():
    last_t = time.monotonic()
    last_detect_t = 0
    while state.phase == MissionPhase.APPROACHING:
        frame = await get_frame()
        now = time.monotonic()
        dt = now - last_t
        last_t = now

        detection = detect(frame)
        if detection is None:
            if now - last_detect_t > 2.0:
                state.phase = MissionPhase.SEARCHING
                await start_spiral_search()
                return
            continue
        last_detect_t = now
        state.marker_locked = True

        # Hedef: marker center → kamera optik merkez
        ex, ey, ez = detection.tvec  # x sağ, y aşağı, z ileri (kamera frame)
        # Body NED: forward = -ez (eğer aşağı bakıyor: forward = X kamera)
        # Eksen mapping kamera mount'una göre yapılır

        vx = pid_x(error_north, dt)
        vy = pid_y(error_east, dt)
        vz = pid_z(error_down, dt)

        await mavlink.send_velocity_target(vx, vy, vz, yaw=0)
```

### 5. Sarmal Arama (SEARCHING fazı)
- Mevcut yüksekliği koru, mevcut konumdan başlayıp Arşimet sarmalı:
  ```
  r(t) = a + b*t,  θ(t) = ω*t
  x = r*cos(θ),  y = r*sin(θ)
  ```
- 5 m yarıçap, 30 sn timeout → ABORT
- Marker bulununca tekrar `APPROACHING`'e dön

### 6. Yaklaşma Profili
- 10 m → 3 m: dikey hızlı (~1.5 m/s)
- 3 m → 1.5 m: yavaş (~0.5 m/s), XY hata < 10 cm bekle
- 1.5 m → teslimat: hover, XY hata < 5 cm bekle → state machine'e "READY_TO_DELIVER" event

## Performans Hedefleri
- Tespit pipeline: ≤ 30 ms / frame
- Servoing döngü jitter: ≤ 10 ms
- Son yaklaşma XY hata: ≤ 5 cm (raporda taahhüt: 14 cm — emniyet payı ile)
- Marker görme menzili: 0.5 m – 10 m (20 cm marker için)

## Testler
- `test_pid.py`: step response, settling time
- `test_aruco_detect.py`: sentetik render edilmiş ArUco görüntülerinde detect
- `test_pose_estimation.py`: bilinen ground truth pozda hata < 2 cm
- `test_spiral.py`: trajektori geometrik doğrulama
- SITL: Gazebo'da ArUco texture'lu ped → simüle iniş, < 14 cm

## Kabul Kriterleri
- 5 ardışık real-world iniş testinde ortalama XY hata < 10 cm
- Marker kaybolma → sarmal → bulma süresi < 15 sn
- Crash yok, servoing → iniş geçişi pürüzsüz

## GÜÇLENDİRMELER (AUDIT)

### G1. solvePnP (deprecated API kaldırma)
OpenCV ≥4.7 `estimatePoseSingleMarkers` deprecated. Kullan:
```python
half = marker_size_m / 2
obj_pts = np.array([[-half, half, 0], [half, half, 0],
                    [half, -half, 0], [-half, -half, 0]], dtype=np.float32)
ok, rvec, tvec = cv2.solvePnP(obj_pts, corners[i], K, dist,
                              flags=cv2.SOLVEPNP_IPPE_SQUARE)
```

### G2. PRECLAND Modu (ArduCopter Yerleşik — Tavsiye)
Custom PID yerine veya yanında ArduCopter PRECLAND kullan:
- Pixhawk paramları: `PLND_ENABLED=1, PLND_TYPE=1 (MAVLink), PLND_EST_TYPE=1 (Kalman)`
- Jetson `LANDING_TARGET` MAVLink mesajı 10 Hz gönderir:
```python
mav.landing_target_send(
    time_usec, target_num=0, frame=MAV_FRAME_BODY_FRD,
    angle_x=atan2(tvec[0], tvec[2]),
    angle_y=atan2(tvec[1], tvec[2]),
    distance=norm(tvec), size_x=0, size_y=0,
)
```
- ArduCopter `LAND` veya `LOITER` modunda otomatik centering.
- Custom PID fallback olarak korunur (PRECLAND başarısızlığında).

### G3. Yaw Mask Düzeltmesi (KRİTİK)
Velocity komutunda yaw 0 absolute = kuzey'e dön. Doğru mask:
```python
type_mask = (
    POSITION_TARGET_TYPEMASK_X_IGNORE | ...Y_IGNORE | ...Z_IGNORE
    | ...AX_IGNORE | ...AY_IGNORE | ...AZ_IGNORE
    | POSITION_TARGET_TYPEMASK_YAW_IGNORE
    | POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
)
```

### G4. Extrinsics (camera + lidar mount offset)
`configs/extrinsics.yaml`:
```yaml
cam_to_body: { x: 0.05, y: 0.0, z: -0.10, roll: 0, pitch: 0, yaw: 0 }
lidar_to_body: { x: 0.03, y: 0.0, z: -0.12 }
```
Pose hesabında transform uygula. Kalibrasyon scripti `scripts/calibrate_extrinsics.py` (chessboard + manuel ölçüm).

### G5. Yaw Alignment
APPROACHING sonunda marker rotation'dan ped yön referansı al, drone yaw → ped yönüne hizala. Alıcı kameraya bakacak şekilde.

### G6. CLAHE Lighting Robustness
`cv2.createCLAHE(clipLimit=2, tileGridSize=(8,8))` ile grayscale frame preprocess → değişen ışıkta detect başarısı +%30.

## Verme
- Çalışan `aruco_servoing.py`
- `calibrate_camera.py` (chessboard kalibrasyonu)
- `tune_pid.py` (log replay + plot)
- README: PID tuning rehberi, mount geometrisi, kamera-marker-IHA frame diyagramı
