"""
config.py — Kokpit İHA otonom teslimat görevi: merkezi konfigürasyon

Tüm ayarlanabilir parametreler burada toplanır. Kod içine "magic number"
gömmüyoruz; uçuş güvenliği parametreleri (irtifa, hız, geofence, eşikler)
tek yerden, gözden geçirilebilir şekilde tutulur.

ÖNEMLİ (drone düşmesin): Bu dosyadaki SAFETY bölümünü saha öncesi mutlaka
gözden geçir. SIMULATION=True iken SITL'e bağlanır, gerçek uçuş yapılmaz.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field


# =============================================================================
# 0. ÇALIŞMA MODU
# =============================================================================
# SIMULATION=True  -> ArduPilot SITL'e bağlanır, sahte kamera/yüz kullanılabilir.
# SIMULATION=False -> Gerçek Pixhawk + Jetson + kameralar.
# Ortam değişkeniyle de override edilebilir: KOKPIT_SIM=0/1
SIMULATION: bool = os.environ.get("KOKPIT_SIM", "1") == "1"


# =============================================================================
# 1. BAĞLANTILAR (MAVLink, LoRa, Kamera)
# =============================================================================
@dataclass
class LinkConfig:
    # --- Pixhawk <-> Jetson MAVLink bağlantısı ---
    # Gerçek donanım: Jetson UART veya USB üzerinden Pixhawk TELEM2'ye bağlanır.
    #   Örn UART:  "/dev/ttyTHS1"   (Jetson Orin Nano UART)  + baud 921600
    #   Örn USB :  "/dev/ttyACM0"
    # SITL: ArduCopter SITL varsayılan olarak udpin:0.0.0.0:14550 yayını yapar;
    #   companion için udp:127.0.0.1:14551 mavproxy çıkışını kullanmak daha sağlıklı.
    mavlink_sim: str = "udpin:0.0.0.0:14551"
    mavlink_real: str = "/dev/ttyTHS1"
    mavlink_baud_real: int = 921600
    heartbeat_timeout_s: float = 5.0   # bu süre boyunca heartbeat yoksa link koptu

    # --- LoRa alıcı (Jetson'a bağlı E32 433MHz) ---
    # E32, UART üzerinden ESP32'den gelen paketi ham byte olarak verir.
    lora_port_sim: str | None = None   # SITL'de LoRa simüle edilir (dosya/enjeksiyon)
    lora_port_real: str = "/dev/ttyUSB0"
    lora_baud: int = 9600              # E32 varsayılan UART hızı

    @property
    def mavlink_connection_string(self) -> str:
        return self.mavlink_sim if SIMULATION else self.mavlink_real


# =============================================================================
# 2. KAMERA
# =============================================================================
@dataclass
class CameraConfig:
    # Alt kamera (ArUco / hassas iniş) — WaveShare IMX219 CSI
    width: int = 1280
    height: int = 720
    fps: int = 30
    # Jetson CSI kamera için GStreamer pipeline (nvarguscamerasrc).
    # USB/laptop testinde index (0) kullanılır.
    use_gstreamer: bool = not SIMULATION
    device_index: int = 0
    sensor_id: int = 0

    # Kamera iç parametreleri (kalibrasyon). camera_calibration.npz varsa oradan
    # yüklenir; yoksa bu varsayılanlar (IMX219 ~ 1280x720) kullanılır.
    # SAHADA mutlaka gerçek kalibrasyon yap (tools/calibrate_camera.py).
    fx: float = 1000.0
    fy: float = 1000.0
    cx: float = 640.0
    cy: float = 360.0
    dist_coeffs: tuple = (0.0, 0.0, 0.0, 0.0, 0.0)
    calibration_file: str = "camera_calibration.npz"

    def gstreamer_pipeline(self) -> str:
        return (
            f"nvarguscamerasrc sensor-id={self.sensor_id} ! "
            f"video/x-raw(memory:NVMM), width={self.width}, height={self.height}, "
            f"framerate={self.fps}/1 ! nvvidconv flip-method=0 ! "
            f"video/x-raw, format=BGRx ! videoconvert ! "
            f"video/x-raw, format=BGR ! appsink drop=1 max-buffers=1"
        )


# =============================================================================
# 3. ARUCO
# =============================================================================
@dataclass
class ArucoConfig:
    # Yer ünitesi (ped) üzerindeki marker.
    dictionary: str = "DICT_5X5_100"   # cv2.aruco sözlüğü
    target_id: int = 0                 # pedin marker ID'si
    marker_length_m: float = 0.30      # kenar uzunluğu (METRE) — fiziksel ölçü!
    # Tespit güveni: bir kareyi "geçerli" saymak için min köşe netliği vb.
    min_detection_frames: int = 3      # üst üste kaç karede görülürse "kilitlendi"


# =============================================================================
# 4. UÇUŞ PARAMETRELERİ (görev profili)
# =============================================================================
@dataclass
class FlightConfig:
    takeoff_altitude_m: float = 8.0     # kalkış sonrası seyir öncesi tırmanma
    cruise_altitude_m: float = 15.0     # hedefe gidiş irtifası (rapor: ~15 m)
    cruise_speed_ms: float = 5.0        # WPNAV_SPEED eşdeğeri (m/s)
    search_altitude_m: float = 10.0     # hedef üzerinde marker arama irtifası

    # Hassas yaklaşma profili
    approach_altitude_m: float = 6.0    # görsel servoya geçiş irtifası
    drop_altitude_m: float = 2.5        # paket bırakma irtifası (rapor: 2-3 m)
    drop_altitude_tolerance_m: float = 0.3

    # Hedefe "vardı" kabul yarıçapı (yatay)
    waypoint_accept_radius_m: float = 1.0
    # Marker merkezleme kabul hatası (yatay) — bu eşiğin altına inince alçal
    center_tolerance_m: float = 0.15    # rapordaki ±14 cm hedefiyle uyumlu

    # İniş sonrası bekleme/disarm
    post_drop_climb_m: float = 5.0      # bırakıştan sonra RTL öncesi yüksel


# =============================================================================
# 5. GÖRSEL SERVO PID
# =============================================================================
@dataclass
class PIDConfig:
    # X (ileri/geri, kuzey) ve Y (sağ/sol, doğu) eksenleri için ayrı PID.
    # Çıkış birimi: m/s (gövde/NED hız komutu). Konservatif başla, sahada artır.
    kp_xy: float = 0.6
    ki_xy: float = 0.05
    kd_xy: float = 0.20
    # Dikey (alçalma) hız kontrolü
    kp_z: float = 0.5
    descent_speed_ms: float = 0.4       # marker merkezlendiğinde alçalma hızı (m/s)
    # Güvenlik limitleri (drone düşmesin): hız komutları kırpılır
    max_xy_speed_ms: float = 1.5        # hassas modda yatay hız tavanı
    max_z_speed_ms: float = 0.6         # dikey hız tavanı
    integral_limit: float = 2.0         # anti-windup
    control_rate_hz: float = 15.0       # servo döngü frekansı


# =============================================================================
# 6. BİYOMETRİK (YÜZ TANIMA)
# =============================================================================
@dataclass
class FaceConfig:
    dataset_dir: str = "faces"          # kayıtlı yüzler (alici_<id>.jpg)
    # face_recognition mesafe eşiği: küçük = daha katı. 0.6 tipik, 0.5 daha katı.
    # Rapor "%90 eşleşme" diyor -> ~0.45 mesafe eşiği civarı tutuyoruz.
    match_distance_threshold: float = 0.45
    min_confidence: float = 0.90        # raporla uyumlu hedef
    model: str = "hog"                  # "hog" (CPU/hızlı) veya "cnn" (GPU/doğru)
    votes_required: int = 5             # kaç karede eşleşme aranacak
    votes_needed_to_pass: int = 3       # bunlardan kaçı eşleşirse "PASS"
    verify_timeout_s: float = 12.0      # doğrulama için maksimum süre


# =============================================================================
# 7. PAKET BIRAKMA (SERVO)
# =============================================================================
@dataclass
class DropperConfig:
    servo_channel: int = 9              # Pixhawk AUX çıkışı (SERVO9_FUNCTION=0/RCx)
    pwm_locked: int = 1100             # kilitli (paket tutuluyor)
    pwm_released: int = 1900           # açık (paket bırakıldı)
    actuation_time_s: float = 1.5      # servonun hareketi tamamlaması için bekleme
    # Servo guard'ları (Sprint 1 P0.3) — drop_altitude_m ± buffer
    # PrecisionApproach lock tolerance ile uyumlu (lock ±0.5 m'de oluyor)
    min_drop_altitude_m: float = 1.0   # bu seviyenin altında bırakma yasak
    max_drop_altitude_m: float = 3.5   # bu seviyenin üstünde bırakma yasak
                                       # (drop_altitude=2.5 + 1.0 buffer)


# =============================================================================
# 8. GÜVENLİK / FAILSAFE (drone düşmesin)
# =============================================================================
@dataclass
class SafetyConfig:
    # Batarya (rapor: kritik eşikte görevi iptal et, RTL)
    battery_warn_voltage: float = 21.6     # 6S ~3.6V/hücre
    battery_low_voltage: float = 22.0      # 6S ~3.67V/hücre -> RTL trigger
    battery_critical_voltage: float = 21.0 # 6S ~3.50V/hücre -> LAND trigger
    battery_min_percent: float = 20.0

    # GPS
    min_satellites: int = 8
    max_hdop: float = 1.5

    # Geofence (göreli, home merkezli) — bu sınır aşılırsa RTL
    geofence_radius_m: float = 150.0
    geofence_max_alt_m: float = 30.0

    # Zaman aşımları (saniye)
    navigation_timeout_s: float = 120.0    # hedefe varış için maks süre
    marker_search_timeout_s: float = 60.0  # sarmal arama maks süre
    overall_mission_timeout_s: float = 600.0

    # Link kaybı -> failsafe RTL
    gcs_link_loss_action: str = "RTL"

    # Sarmal (spiral) arama parametreleri
    spiral_step_m: float = 1.5             # tur başına yarıçap artışı
    spiral_max_radius_m: float = 12.0
    spiral_speed_ms: float = 1.5


# =============================================================================
# Toplu erişim
# =============================================================================
@dataclass
class Config:
    link: LinkConfig = field(default_factory=LinkConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    aruco: ArucoConfig = field(default_factory=ArucoConfig)
    flight: FlightConfig = field(default_factory=FlightConfig)
    pid: PIDConfig = field(default_factory=PIDConfig)
    face: FaceConfig = field(default_factory=FaceConfig)
    dropper: DropperConfig = field(default_factory=DropperConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    simulation: bool = SIMULATION

    def validate(self) -> list[str]:
        """Mantıksal tutarlılık kontrolü. Saha öncesi çağrılmalı."""
        errors: list[str] = []
        f, s = self.flight, self.safety
        if f.drop_altitude_m <= 0:
            errors.append("drop_altitude_m > 0 olmalı")
        if not (1.5 <= f.drop_altitude_m <= 3.5):
            errors.append("drop_altitude_m 2-3 m hedefi dışında (rapor şartı)")
        if f.cruise_altitude_m > s.geofence_max_alt_m:
            errors.append("cruise_altitude_m geofence_max_alt_m'i aşıyor")
        if f.approach_altitude_m < f.drop_altitude_m:
            errors.append("approach_altitude_m >= drop_altitude_m olmalı")
        if self.pid.max_xy_speed_ms > f.cruise_speed_ms + 5:
            errors.append("max_xy_speed_ms aşırı yüksek")
        if self.face.match_distance_threshold <= 0:
            errors.append("match_distance_threshold > 0 olmalı")
        if self.dropper.pwm_locked == self.dropper.pwm_released:
            errors.append("dropper kilitli/açık PWM aynı olamaz")
        return errors


# Tekil global config örneği
CFG = Config()


if __name__ == "__main__":
    errs = CFG.validate()
    print("SIMULATION:", CFG.simulation)
    print("MAVLink:", CFG.link.mavlink_connection_string)
    if errs:
        print("KONFIG HATALARI:")
        for e in errs:
            print("  -", e)
    else:
        print("Konfig doğrulandı: OK")
