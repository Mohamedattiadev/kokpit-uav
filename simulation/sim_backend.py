"""
sim_backend.py — Yazılım-içi fizik simülasyonu (ArduPilot SITL gerektirmeden)

İki bileşen:
  * FakeDrone     : DroneController ile AYNI arayüze sahip, basit fizik modelli
                    sahte uçuş kontrolcüsü. goto/velocity/takeoff/RTL/LAND simüle eder.
  * SimDownCamera : İHA'nın marker'a göre konumuna göre alt kamera görüntüsünü
                    sentezler — gerçek ArUco tespiti + görsel servo bu görüntü
                    üzerinden kapalı döngü çalışır.

Bu backend hem otomatik testte (tests/test_mission_integration.py) hem de
"simulation/software_demo.py" yazılım demosunda kullanılır. Uçuş mantığını GERÇEK
kameralar/Pixhawk olmadan uçtan uca doğrulamak içindir.

NOT: Bu, ArduPilot SITL'in YERİNE geçmez; saha öncesi mutlaka gerçek SITL'de
(run_sitl.sh) de test edin. Burası mantık doğrulama katmanıdır.
"""
from __future__ import annotations
import math
import threading
import time

import numpy as np
import cv2

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from mavlink_interface import Telemetry, haversine_m  # noqa: E402
from config import CFG  # noqa: E402

M_PER_DEG = 111320.0


class FakeDrone:
    """DroneController arayüzünü taklit eden fizik simülatörü."""

    def __init__(self, home_lat=39.942000, home_lon=32.847000):
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.lat = home_lat
        self.lon = home_lon
        self.alt = 0.0
        self.heading = 0.0
        self.armed = False
        self.mode = "STABILIZE"
        self.servo_pwm = {}
        self._target = None            # (lat, lon, alt)
        self._vel = (0.0, 0.0, 0.0)    # body (fwd, right, down)
        self._vel_ts = 0.0
        self._lock = threading.Lock()
        self._running = False
        self._t = None
        self.battery_voltage = 24.0
        self.crashed = False

    # --------------------------------------------------- yaşam döngüsü
    def connect(self, timeout=30.0):
        self._running = True
        self._t = threading.Thread(target=self._physics_loop, daemon=True)
        self._t.start()

    def close(self):
        self._running = False
        if self._t:
            self._t.join(timeout=1.0)

    # --------------------------------------------------- telemetri
    def telemetry(self) -> Telemetry:
        with self._lock:
            return Telemetry(
                lat=self.lat, lon=self.lon, alt_rel=self.alt,
                alt_amsl=900 + self.alt, heading=self.heading,
                battery_voltage=self.battery_voltage, battery_remaining=80,
                satellites=14, hdop=0.7, fix_type=3,
                armed=self.armed, mode=self.mode, ekf_ok=True,
                last_heartbeat=time.time(), last_update=time.time())

    def link_alive(self):
        return self._running

    # --------------------------------------------------- komutlar
    def wait_ready_to_arm(self, timeout=60.0):
        return True

    def set_mode(self, mode, timeout=5.0):
        with self._lock:
            self.mode = mode
            if mode == "RTL":
                self._target = (self.home_lat, self.home_lon,
                                max(self.alt, CFG.flight.cruise_altitude_m))
                self._vel = (0, 0, 0)
        return True

    def arm(self, timeout=10.0, force=False):
        with self._lock:
            self.armed = True
            self.mode = "GUIDED"
        return True

    def disarm(self, timeout=10.0, force=False):
        with self._lock:
            self.armed = False
        return True

    def takeoff(self, altitude, timeout=40.0):
        with self._lock:
            self.mode = "GUIDED"
            self._target = (self.lat, self.lon, altitude)
        start = time.time()
        while time.time() - start < timeout:
            if self.alt >= altitude * 0.95:
                return True
            time.sleep(0.05)
        return self.alt > altitude * 0.5

    def goto_global(self, lat, lon, alt_rel):
        with self._lock:
            self.mode = "GUIDED"
            self._target = (lat, lon, alt_rel)
            self._vel = (0, 0, 0)

    def send_velocity_body(self, v_fwd, v_right, v_down, yaw_rate=0.0):
        # güvenlik kırpması (gerçek arayüzle aynı davranış)
        v_fwd = _clip(v_fwd, CFG.pid.max_xy_speed_ms)
        v_right = _clip(v_right, CFG.pid.max_xy_speed_ms)
        v_down = _clip(v_down, CFG.pid.max_z_speed_ms)
        with self._lock:
            self._vel = (v_fwd, v_right, v_down)
            self._vel_ts = time.time()
            self._target = None  # velocity moduna geç

    def send_velocity_ned(self, vx, vy, vz, yaw_rate=0.0):
        self.send_velocity_body(vx, vy, vz, yaw_rate)

    def set_servo(self, channel, pwm):
        with self._lock:
            self.servo_pwm[channel] = pwm

    def distance_to(self, lat, lon):
        with self._lock:
            return haversine_m(self.lat, self.lon, lat, lon)

    # --------------------------------------------------- fizik
    def _physics_loop(self):
        dt = 0.05
        while self._running:
            t0 = time.time()
            self._step(dt)
            elapsed = time.time() - t0
            if elapsed < dt:
                time.sleep(dt - elapsed)

    def _step(self, dt):
        with self._lock:
            if not self.armed:
                return
            # RTL/LAND otomatik iniş
            if self.mode == "LAND":
                self.alt = max(0.0, self.alt - 0.8 * dt * 10)
                if self.alt <= 0.05:
                    self.armed = False
                return
            # Velocity komutu taze mi? (0.5 sn'den eskiyse sıfırla)
            vel_active = (time.time() - self._vel_ts) < 0.5 and self._target is None
            if vel_active:
                fwd, right, down = self._vel
                # heading=0 -> fwd=Kuzey, right=Doğu
                self.lat += (fwd * dt) / M_PER_DEG
                self.lon += (right * dt) / (M_PER_DEG * math.cos(math.radians(self.lat)))
                self.alt = max(0.0, self.alt - down * dt)
            elif self._target is not None:
                tlat, tlon, talt = self._target
                # yatay
                dn = (tlat - self.lat) * M_PER_DEG
                de = (tlon - self.lon) * M_PER_DEG * math.cos(math.radians(self.lat))
                dist = math.hypot(dn, de)
                speed = CFG.flight.cruise_speed_ms
                if dist > 1e-3:
                    step = min(dist, speed * dt)
                    self.lat += (dn / dist) * step / M_PER_DEG
                    self.lon += (de / dist) * step / (M_PER_DEG * math.cos(math.radians(self.lat)))
                # dikey
                climb = 2.0  # m/s
                if abs(talt - self.alt) > 1e-2:
                    self.alt += _clip(talt - self.alt, climb * dt)
                # RTL: home'a varınca in ve disarm
                if self.mode == "RTL" and dist < 1.0:
                    self.alt = max(0.0, self.alt - 1.0 * dt * 10)
                    if self.alt <= 0.05:
                        self.armed = False


class SimDownCamera:
    """İHA'nın marker'a göre konumuna göre alt kamera karesi üretir."""

    def __init__(self, drone: FakeDrone, marker_lat, marker_lon,
                 marker_len_m=None, marker_id=None):
        self.drone = drone
        self.marker_lat = marker_lat
        self.marker_lon = marker_lon
        self.marker_len = marker_len_m or CFG.aruco.marker_length_m
        self.marker_id = marker_id if marker_id is not None else CFG.aruco.target_id
        c = CFG.camera
        self.w, self.h = c.width, c.height
        self.fx, self.fy, self.cx, self.cy = c.fx, c.fy, c.cx, c.cy
        d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, CFG.aruco.dictionary))
        size = 400
        if hasattr(cv2.aruco, "generateImageMarker"):
            bit = cv2.aruco.generateImageMarker(d, self.marker_id, size)
        else:
            bit = cv2.aruco.drawMarker(d, self.marker_id, size)
        # beyaz kenar (quiet zone) ekle — tespit için şart
        b = 80
        canvas = np.full((size + 2 * b, size + 2 * b), 255, np.uint8)
        canvas[b:b + size, b:b + size] = bit
        self.marker_img = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)

    def read(self):
        t = self.drone.telemetry()
        frame = np.full((self.h, self.w, 3), 180, np.uint8)  # zemin (gri)
        h_alt = max(0.3, t.alt_rel)
        north = (self.marker_lat - t.lat) * M_PER_DEG
        east = (self.marker_lon - t.lon) * M_PER_DEG * math.cos(math.radians(t.lat))
        # Araç yönüne (heading) göre gövde çerçevesine döndür (SITL'de yaw değişebilir)
        psi = math.radians(t.heading)
        fwd = north * math.cos(psi) + east * math.sin(psi)
        right = -north * math.sin(psi) + east * math.cos(psi)
        # alta bakan pinhole projeksiyonu: image-up = gövde ileri, image-right = gövde sağ
        u = self.cx + self.fx * (right / h_alt)
        v = self.cy - self.fy * (fwd / h_alt)
        # ArUco KOD bölgesi piksel boyu (fiziksel marker_len'e karşılık)
        code_px = self.fx * self.marker_len / h_alt
        if code_px < 14:
            return True, frame  # çok yüksek/küçük -> marker görünmez
        # marker_img kod(400) + quiet zone(2*80) = 560 px. Kodu code_px yap.
        scale = code_px / 400.0
        size_px = int(min(560 * scale, max(self.w, self.h) * 2))
        m = cv2.resize(self.marker_img, (size_px, size_px))
        x0 = int(u - size_px / 2)
        y0 = int(v - size_px / 2)
        # tamamen kare dışındaysa görünmez
        if x0 + size_px < 0 or y0 + size_px < 0 or x0 >= self.w or y0 >= self.h:
            return True, frame
        # kırparak yerleştir
        xs, ys = max(0, x0), max(0, y0)
        xe, ye = min(self.w, x0 + size_px), min(self.h, y0 + size_px)
        mx0, my0 = xs - x0, ys - y0
        frame[ys:ye, xs:xe] = m[my0:my0 + (ye - ys), mx0:mx0 + (xe - xs)]
        return True, frame

    def release(self):
        pass


def _clip(v, limit):
    return max(-limit, min(limit, v))
