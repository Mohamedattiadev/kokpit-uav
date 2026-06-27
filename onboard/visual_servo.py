"""
visual_servo.py — ArUco tabanlı hassas yaklaşma (Visual Servoing) + sarmal arama

Rapor 3.1.5 / 3.3.1.3: hedefe varınca GPS ikincil plana alınır; kamera+lidar
füzyonuyla, PID kontrol döngüsü marker'ı görüntü merkezine getirir ve İHA
kontrollü şekilde paket bırakma irtifasına (2-3 m) alçalır.

Güvenlik (drone düşmesin):
  * Tüm hız komutları config limitlerine kırpılır.
  * Marker kaybolursa önce yerinde tutunur (sıfır hız), sonra sarmal aramaya geçer.
  * Alçalma SADECE yatay hata küçükken yapılır (marker'ın dışına kayıp inmez).
  * Link/abort kontrolü her döngüde yapılır.
"""
from __future__ import annotations
import math
import time

from config import CFG
from mavlink_interface import DroneController
from aruco_detector import ArucoDetector, Detection
from pid import PID

# Kamera montaj yönü işaretleri. Eğer marker görünür ama İHA TERS yöne kaçıyorsa
# bu işaretleri çevir (sahada hızlı kalibrasyon). +1 / -1.
FWD_SIGN = 1.0    # offset_fwd_m -> ileri hız işareti
RIGHT_SIGN = 1.0  # offset_right_m -> sağ hız işareti


class PrecisionApproach:
    def __init__(self, drone: DroneController, detector: ArucoDetector, camera,
                 abort_check=None, *, precland_complement: bool = True):
        """precland_complement=True iken her tespit sonrası ArduCopter'a
        LANDING_TARGET MAVLink mesajı da gönderilir (PRECLAND yerleşik
        Kalman'ı ile custom PID paralel çalışır). Rapor "Visual Servoing
        PID" taahhüdüne uyumlu — PID primary, PRECLAND complement."""
        self.drone = drone
        self.detector = detector
        self.camera = camera
        self.abort_check = abort_check or (lambda: False)
        self.precland_complement = precland_complement
        p = CFG.pid
        self.pid_fwd = PID(p.kp_xy, p.ki_xy, p.kd_xy,
                           output_limit=p.max_xy_speed_ms,
                           integral_limit=p.integral_limit)
        self.pid_right = PID(p.kp_xy, p.ki_xy, p.kd_xy,
                             output_limit=p.max_xy_speed_ms,
                             integral_limit=p.integral_limit)

    # ----------------------------------------------------- yardımcılar
    def _errors(self, det: Detection):
        """Marker'ın gövde-çerçevesi yatay hatası (metre): (ileri, sağ)."""
        if det.distance_m > 0.05:
            return FWD_SIGN * det.offset_fwd_m, RIGHT_SIGN * det.offset_right_m
        # Poz yoksa: normalize pikselden irtifaya ölçekleyerek kaba tahmin.
        alt = max(0.5, self.drone.telemetry().alt_rel)
        # image: +x sağ, +y aşağı. ileri = -y (image yukarısı ileri).
        scale = alt * 0.5  # FOV'a bağlı kaba katsayı; pozla beraber ikincildir
        return (FWD_SIGN * (-det.offset_norm_y) * scale,
                RIGHT_SIGN * det.offset_norm_x * scale)

    # ----------------------------------------------------- ana döngü
    def run(self, target_alt: float | None = None, on_frame=None) -> bool:
        """Marker'ı merkezleyip target_alt'e (paket irtifası) alçal.
        Başarılı (merkezli + irtifada) ise True döner."""
        target_alt = target_alt if target_alt is not None else CFG.flight.drop_altitude_m
        f, p, s = CFG.flight, CFG.pid, CFG.safety
        self.pid_fwd.reset()
        self.pid_right.reset()
        dt = 1.0 / p.control_rate_hz
        lost_frames = 0
        lost_limit = int(p.control_rate_hz * 1.5)   # ~1.5 sn kayıp -> arama
        locked_frames = 0
        start = time.time()

        print(f"[SERVO] Hassas yaklaşma başladı, hedef irtifa {target_alt:.1f} m")
        while True:
            loop_t = time.time()
            if self.abort_check():
                self._brake()
                print("[SERVO] ABORT istendi")
                return False
            if not self.drone.link_alive():
                self._brake()
                print("[SERVO] Link koptu — yaklaşma durduruldu")
                return False
            if time.time() - start > s.marker_search_timeout_s + 60:
                self._brake()
                print("[SERVO] Yaklaşma zaman aşımı")
                return False

            ok, frame = self.camera.read()
            det = self.detector.detect(frame) if ok else Detection(found=False)
            if on_frame:
                on_frame(frame, det)

            if not det.found:
                lost_frames += 1
                locked_frames = 0
                self._brake()   # yerinde tutun
                if lost_frames >= lost_limit:
                    print("[SERVO] Marker kayboldu -> sarmal arama")
                    if not self.spiral_search(on_frame=on_frame):
                        print("[SERVO] Sarmal arama başarısız")
                        return False
                    lost_frames = 0
                _sleep_to_rate(loop_t, dt)
                continue

            lost_frames = 0
            err_fwd, err_right = self._errors(det)
            horiz_err = math.hypot(err_fwd, err_right)

            # PRECLAND complement — Pixhawk yerleşik Kalman'a da besle
            if self.precland_complement and det.distance_m > 0.05:
                try:
                    ax = math.atan2(det.offset_right_m, det.distance_m)
                    ay = math.atan2(det.offset_fwd_m, det.distance_m)
                    self.drone.send_landing_target(
                        ax, ay, det.distance_m)
                except Exception:
                    pass   # PRECLAND opsiyonel, hata custom PID'i durdurmasın

            v_fwd = self.pid_fwd.update(err_fwd, dt)
            v_right = self.pid_right.update(err_right, dt)

            alt = self.drone.telemetry().alt_rel
            # Alçalma sadece kabaca merkezdeyken (marker dışına kaymasın)
            descend_gate = f.center_tolerance_m * 2.5
            if horiz_err < descend_gate and alt > target_alt:
                v_down = min(p.descent_speed_ms,
                             p.kp_z * (alt - target_alt))
            else:
                v_down = 0.0
            v_down = max(-p.max_z_speed_ms, min(p.max_z_speed_ms, v_down))

            self.drone.send_velocity_body(v_fwd, v_right, v_down)

            # Kilitlenme: merkezli + irtifada
            at_alt = abs(alt - target_alt) <= f.drop_altitude_tolerance_m
            centered = horiz_err <= f.center_tolerance_m
            if at_alt and centered:
                locked_frames += 1
                if locked_frames >= CFG.aruco.min_detection_frames:
                    self._brake()
                    print(f"[SERVO] KİLİTLENDİ: irtifa {alt:.2f} m, "
                          f"yatay hata {horiz_err*100:.1f} cm")
                    return True
            else:
                locked_frames = 0

            _sleep_to_rate(loop_t, dt)

    def _brake(self):
        self.drone.send_velocity_body(0.0, 0.0, 0.0)

    # ----------------------------------------------------- sarmal arama
    def spiral_search(self, on_frame=None) -> bool:
        """Mevcut konum çevresinde genişleyen sarmal waypoint'ler tarar.
        Marker görülürse True döner ve İHA marker üstünde durur."""
        s, f = CFG.safety, CFG.flight
        t0 = self.drone.telemetry()
        base_lat, base_lon = t0.lat, t0.lon
        search_alt = f.search_altitude_m
        start = time.time()

        # Arşimet sarmalı: r = step * theta/(2pi)
        theta = 0.0
        while time.time() - start < s.marker_search_timeout_s:
            if self.abort_check() or not self.drone.link_alive():
                self._brake()
                return False
            r = s.spiral_step_m * theta / (2 * math.pi)
            if r > s.spiral_max_radius_m:
                print("[SERVO] Sarmal max yarıçapa ulaştı, marker yok")
                return False
            dN = r * math.cos(theta)
            dE = r * math.sin(theta)
            tlat = base_lat + (dN / 111320.0)
            tlon = base_lon + (dE / (111320.0 * math.cos(math.radians(base_lat))))
            self.drone.goto_global(tlat, tlon, search_alt)

            # Bu segmentte marker tara
            seg_start = time.time()
            while time.time() - seg_start < 2.0:
                ok, frame = self.camera.read()
                det = self.detector.detect(frame) if ok else Detection(found=False)
                if on_frame:
                    on_frame(frame, det)
                if det.found:
                    self._brake()
                    print("[SERVO] Marker sarmal aramada bulundu")
                    return True
                time.sleep(0.05)
            theta += math.pi / 2  # çeyrek tur ilerle
        return False


def _sleep_to_rate(loop_start: float, dt: float):
    elapsed = time.time() - loop_start
    if elapsed < dt:
        time.sleep(dt - elapsed)
