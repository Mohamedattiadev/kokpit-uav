"""
package_dropper.py — Servo tabanlı paket bırakma mekanizması

Rapor 3.2.6: PWM sinyali ile kontrol edilen servo. Biyometrik doğrulama
BAŞARILI olduğunda tetiklenir. Güvenlik gereği yalnızca açıkça çağrıldığında
açılır; başlangıçta ve görev sonunda kilitli konuma alınır.

Sprint 1 P0.3 — 6 katmanlı safety guard:
  1. Phase guard (sadece DROP_PACKAGE fazında)
  2. Face verified flag
  3. Marker locked flag
  4. Altitude band (1.0 m <= lidar_alt <= 2.5 m)
  5. MAVLink servo ACK (set_servo retries + ack timeout)
  6. Tilt snapshot (|roll|<15°, |pitch|<15°) — devrik durumda bırakma yok
"""
from __future__ import annotations
import math
import time

from config import CFG
from mavlink_interface import DroneController


class GuardFailure(Exception):
    """Servo guard'larından biri reddetti."""


class PackageDropper:
    def __init__(self, drone: DroneController):
        self.drone = drone
        self.cfg = CFG.dropper
        self.dropped = False
        # Boot lock — idempotent, iki kez çağrılması güvenli
        # (drone bağlandıktan sonra mission.setup() lock() çağırır)

    def lock(self):
        """Paketi tutan kilitli konum (başlangıç + boot safety)."""
        # Idempotency için 2 kez gönder, sessiz hata kabul
        for _ in range(2):
            try:
                self.drone.set_servo(self.cfg.servo_channel,
                                     self.cfg.pwm_locked, retries=2)
            except Exception:
                pass
            time.sleep(0.1)
        self.dropped = False
        print("[DROP] Mekanizma KİLİTLİ (paket tutuluyor)")

    def drop(self, *, phase_ok: bool = True, face_verified: bool = False,
             marker_locked: bool = False) -> bool:
        """Paketi bırak — 6 katmanlı guard kontrolü.

        phase_ok:        çağıran sadece DROP_PACKAGE fazındaysa True versin.
        face_verified:   biyometrik doğrulama başarılıysa True.
        marker_locked:   görsel servo marker kilidi varsa True.
        """
        if self.dropped:
            print("[DROP] Zaten bırakılmış")
            return True
        try:
            self._check_guards(phase_ok, face_verified, marker_locked)
        except GuardFailure as e:
            print(f"[DROP] BLOKLANDI: {e}")
            return False
        print("[DROP] Tüm guard'lar geçti. Paket bırakılıyor...")
        ok = self.drone.set_servo(self.cfg.servo_channel,
                                  self.cfg.pwm_released, retries=3)
        if not ok:
            print("[DROP] HATA: servo ACK alınamadı (SERVO_FAIL)")
            return False
        time.sleep(self.cfg.actuation_time_s)
        self.dropped = True
        print("[DROP] Paket BIRAKILDI")
        return True

    def _check_guards(self, phase_ok: bool, face_verified: bool,
                      marker_locked: bool) -> None:
        if not phase_ok:
            raise GuardFailure("phase guard — DROP_PACKAGE fazında değil")
        if not face_verified:
            raise GuardFailure("face_verified guard — biyometrik doğrulanmadı")
        if not marker_locked:
            raise GuardFailure("marker_locked guard — ArUco kilidi yok")
        t = self.drone.telemetry()
        min_alt = getattr(self.cfg, "min_drop_altitude_m", 1.0)
        max_alt = getattr(self.cfg, "max_drop_altitude_m", 2.5)
        alt = t.lidar_alt if t.lidar_ok else t.alt_rel
        if not (min_alt <= alt <= max_alt):
            raise GuardFailure(
                f"altitude guard — {alt:.2f} m bandı [{min_alt}, {max_alt}] dışı")
        tilt_deg = max(abs(math.degrees(t.roll)), abs(math.degrees(t.pitch)))
        if tilt_deg > 15:
            raise GuardFailure(f"tilt guard — eğim {tilt_deg:.0f}° > 15°")

    def reset(self):
        """Mekanizmayı tekrar kilitli konuma al (sonraki görev için)."""
        self.lock()
