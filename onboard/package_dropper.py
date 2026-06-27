"""
package_dropper.py — Servo tabanlı paket bırakma mekanizması

Rapor 3.2.6: PWM sinyali ile kontrol edilen servo. Biyometrik doğrulama
BAŞARILI olduğunda tetiklenir. Güvenlik gereği yalnızca açıkça çağrıldığında
açılır; başlangıçta ve görev sonunda kilitli konuma alınır.
"""
from __future__ import annotations
import time

from config import CFG
from mavlink_interface import DroneController


class PackageDropper:
    def __init__(self, drone: DroneController):
        self.drone = drone
        self.cfg = CFG.dropper
        self.dropped = False

    def lock(self):
        """Paketi tutan kilitli konum (başlangıç güvenli durumu)."""
        self.drone.set_servo(self.cfg.servo_channel, self.cfg.pwm_locked)
        self.dropped = False
        print("[DROP] Mekanizma KİLİTLİ (paket tutuluyor)")

    def drop(self) -> bool:
        """Paketi bırak. Servoyu açık konuma al, hareket için bekle."""
        if self.dropped:
            print("[DROP] Zaten bırakılmış")
            return True
        print("[DROP] Paket bırakılıyor...")
        self.drone.set_servo(self.cfg.servo_channel, self.cfg.pwm_released)
        time.sleep(self.cfg.actuation_time_s)
        self.dropped = True
        print("[DROP] Paket BIRAKILDI")
        return True

    def reset(self):
        """Mekanizmayı tekrar kilitli konuma al (sonraki görev için)."""
        self.lock()
