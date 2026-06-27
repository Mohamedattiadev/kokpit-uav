"""
mavlink_interface.py — Pixhawk (ArduCopter) ile MAVLink köprüsü (pymavlink)

İHA görev yazılımının uçuş kontrolcüsüyle konuştuğu TEK katman burasıdır.
Diğer modüller (mission, visual_servo, dropper) doğrudan pymavlink çağırmaz;
hepsi DroneController üzerinden gider. Böylece güvenlik mantığı tek yerde toplanır.

Özellikler:
  * Arka planda telemetri okuyan iş parçacığı (en güncel pozisyon/batarya/GPS).
  * GUIDED mod komutları: arm, takeoff, goto (global), velocity (NED/body).
  * Servo (paket bırakma) ve mod değişimi (RTL/LAND/BRAKE).
  * Failsafe için sağlık göstergeleri (batarya, uydu, HDOP, link).

Hedef firmware: ArduCopter 4.x. SITL ile birebir aynı arayüz.
"""
from __future__ import annotations
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from pymavlink import mavutil

from config import CFG

# ArduCopter uçuş modları (isim -> custom_mode). mode_mapping() ile de alınır.
COPTER_MODES = {
    "STABILIZE": 0, "GUIDED": 4, "LOITER": 5, "RTL": 6,
    "LAND": 9, "BRAKE": 17, "AUTO": 3, "POSHOLD": 16,
}

EARTH_RADIUS_M = 6378137.0


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """İki koordinat arası yatay mesafe (metre)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class Telemetry:
    lat: float = 0.0
    lon: float = 0.0
    alt_rel: float = 0.0      # home'a göre irtifa (m)
    alt_amsl: float = 0.0
    heading: float = 0.0      # derece
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    battery_voltage: float = 0.0
    battery_remaining: float = 100.0
    satellites: int = 0
    hdop: float = 99.9
    fix_type: int = 0
    armed: bool = False
    mode: str = "UNKNOWN"
    ekf_ok: bool = False
    last_heartbeat: float = 0.0
    last_update: float = 0.0
    # Sprint 0/1 — eklenen alanlar
    lidar_alt: float = 0.0          # m, RANGEFINDER mesajından
    lidar_ok: bool = False
    lidar_last_update: float = 0.0
    roll: float = 0.0               # rad, ATTITUDE
    pitch: float = 0.0
    yaw: float = 0.0
    accel_z_g: float = 1.0          # g cinsinden dikey ivme, crash detection


class DroneController:
    def __init__(self, connection_string: Optional[str] = None,
                 baud: Optional[int] = None):
        self.conn_str = connection_string or CFG.link.mavlink_connection_string
        self.baud = baud or (None if CFG.simulation else CFG.link.mavlink_baud_real)
        self.master: Optional[mavutil.mavfile] = None
        self.tel = Telemetry()
        self.home_lat: Optional[float] = None
        self.home_lon: Optional[float] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    # ----------------------------------------------------------------- bağlantı
    def connect(self, timeout: float = 30.0) -> None:
        if self.master is not None and self.link_alive():
            return   # zaten bağlı (çift connect güvenli)
        print(f"[MAV] Bağlanılıyor: {self.conn_str}")
        if self.baud:
            self.master = mavutil.mavlink_connection(self.conn_str, baud=self.baud)
        else:
            self.master = mavutil.mavlink_connection(self.conn_str)
        hb = self.master.wait_heartbeat(timeout=timeout)
        if hb is None:
            raise TimeoutError("Heartbeat alınamadı — bağlantıyı kontrol et")
        print(f"[MAV] Heartbeat OK (sys {self.master.target_system}, "
              f"comp {self.master.target_component})")
        self._request_streams()
        self._start_rx()

    def _request_streams(self):
        # Mesaj-bazlı stream rate (eski MAV_DATA_STREAM_ALL yetersiz).
        # ATTITUDE 20 Hz crash detection için kritik.
        rates_hz = {
            mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE: 20,
            mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT: 5,
            mavutil.mavlink.MAVLINK_MSG_ID_RANGEFINDER: 10,
            mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS: 1,
            mavutil.mavlink.MAVLINK_MSG_ID_RAW_IMU: 20,
            mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT: 2,
            mavutil.mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT: 2,
            mavutil.mavlink.MAVLINK_MSG_ID_HOME_POSITION: 1,
            mavutil.mavlink.MAVLINK_MSG_ID_SYSTEM_TIME: 1,
        }
        for msg_id, hz in rates_hz.items():
            interval_us = int(1_000_000 / hz)
            try:
                self._command_long(
                    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                    msg_id, interval_us)
            except Exception as e:
                print(f"[MAV] stream {msg_id} ayarı uyarı: {e}")
        # Geriye dönük uyum için ALL stream'i de aktif tut
        try:
            self.master.mav.request_data_stream_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
        except Exception:
            pass

    def _start_rx(self):
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def _rx_loop(self):
        while self._running and self.master:
            msg = self.master.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue
            self._handle_msg(msg)

    def _handle_msg(self, msg):
        t = msg.get_type()
        now = time.time()
        with self._lock:
            self.tel.last_update = now
            if t == "HEARTBEAT":
                self.tel.last_heartbeat = now
                self.tel.armed = bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                self.tel.mode = mavutil.mode_string_v10(msg)
            elif t == "GLOBAL_POSITION_INT":
                self.tel.lat = msg.lat / 1e7
                self.tel.lon = msg.lon / 1e7
                self.tel.alt_amsl = msg.alt / 1000.0
                self.tel.alt_rel = msg.relative_alt / 1000.0
                self.tel.vx = msg.vx / 100.0
                self.tel.vy = msg.vy / 100.0
                self.tel.vz = msg.vz / 100.0
                self.tel.heading = msg.hdg / 100.0
            elif t == "GPS_RAW_INT":
                self.tel.satellites = msg.satellites_visible
                self.tel.fix_type = msg.fix_type
                self.tel.hdop = msg.eph / 100.0 if msg.eph != 65535 else 99.9
            elif t in ("SYS_STATUS",):
                self.tel.battery_voltage = msg.voltage_battery / 1000.0
                self.tel.battery_remaining = max(0, msg.battery_remaining)
            elif t == "BATTERY_STATUS":
                if msg.voltages and msg.voltages[0] != 65535:
                    self.tel.battery_voltage = sum(
                        v for v in msg.voltages if v != 65535) / 1000.0
            elif t == "EKF_STATUS_REPORT":
                # EKF_STATUS_REPORT bit flags (ardupilotmega dialect, not present
                # as named constants in all pymavlink versions — use literals).
                EKF_ATTITUDE = 0x01
                EKF_VELOCITY_HORIZ = 0x02
                EKF_POS_HORIZ_ABS = 0x08
                flags = msg.flags
                self.tel.ekf_ok = bool(flags & EKF_ATTITUDE) and \
                    bool(flags & EKF_POS_HORIZ_ABS) and \
                    bool(flags & EKF_VELOCITY_HORIZ)
            elif t == "RANGEFINDER":
                # ArduCopter rangefinder (lidar) — TFS20 mesafe metre
                self.tel.lidar_alt = msg.distance
                self.tel.lidar_ok = True
                self.tel.lidar_last_update = now
            elif t == "ATTITUDE":
                self.tel.roll = msg.roll
                self.tel.pitch = msg.pitch
                self.tel.yaw = msg.yaw
            elif t == "RAW_IMU":
                # Accel m/s² (mg → g cinsi için 1000'e böl); crash detection için
                self.tel.accel_z_g = msg.zacc / 1000.0
            elif t == "HOME_POSITION":
                self.home_lat = msg.latitude / 1e7
                self.home_lon = msg.longitude / 1e7

    def telemetry(self) -> Telemetry:
        with self._lock:
            # kopya benzeri snapshot
            return Telemetry(**self.tel.__dict__)

    def link_alive(self) -> bool:
        return (time.time() - self.tel.last_heartbeat) < CFG.link.heartbeat_timeout_s

    def close(self):
        self._running = False
        if self._rx_thread:
            self._rx_thread.join(timeout=2.0)
        if self.master:
            self.master.close()

    # ----------------------------------------------------------------- komutlar
    def _command_long(self, command, p1=0, p2=0, p3=0, p4=0, p5=0, p6=0, p7=0):
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            command, 0, p1, p2, p3, p4, p5, p6, p7)

    def set_mode(self, mode: str, timeout: float = 5.0) -> bool:
        mapping = self.master.mode_mapping() or COPTER_MODES
        if mode not in mapping:
            raise ValueError(f"Bilinmeyen mod: {mode}")
        self.master.set_mode(mapping[mode])
        start = time.time()
        while time.time() - start < timeout:
            if self.telemetry().mode == mode:
                print(f"[MAV] Mod -> {mode}")
                return True
            time.sleep(0.1)
        print(f"[MAV] UYARI: mod {mode} doğrulanamadı")
        return False

    def wait_ready_to_arm(self, timeout: float = 60.0) -> bool:
        """EKF/GPS hazır olana kadar bekle (pre-arm)."""
        start = time.time()
        while time.time() - start < timeout:
            t = self.telemetry()
            if (t.fix_type >= 3 and t.satellites >= CFG.safety.min_satellites
                    and t.hdop <= CFG.safety.max_hdop):
                print(f"[MAV] Arm'a hazır (sat={t.satellites}, hdop={t.hdop:.2f})")
                return True
            time.sleep(0.5)
        print("[MAV] Arm öncesi kontroller zaman aşımı")
        return False

    def arm(self, timeout: float = 10.0, force: bool = False) -> bool:
        self._command_long(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            1, 21196 if force else 0)
        start = time.time()
        while time.time() - start < timeout:
            if self.telemetry().armed:
                print("[MAV] ARMED")
                return True
            time.sleep(0.2)
        print("[MAV] ARM başarısız")
        return False

    def disarm(self, timeout: float = 10.0, force: bool = False) -> bool:
        self._command_long(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 21196 if force else 0)
        start = time.time()
        while time.time() - start < timeout:
            if not self.telemetry().armed:
                print("[MAV] DISARMED")
                return True
            time.sleep(0.2)
        return False

    def takeoff(self, altitude: float, timeout: float = 40.0) -> bool:
        """GUIDED modda dikey kalkış (VTOL)."""
        self._command_long(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                           0, 0, 0, 0, 0, 0, altitude)
        start = time.time()
        while time.time() - start < timeout:
            alt = self.telemetry().alt_rel
            if alt >= altitude * 0.95:
                print(f"[MAV] Kalkış tamam: {alt:.1f} m")
                return True
            time.sleep(0.3)
        print(f"[MAV] Kalkış hedefe ulaşmadı ({self.telemetry().alt_rel:.1f} m)")
        return False

    def goto_global(self, lat: float, lon: float, alt_rel: float):
        """GUIDED modda global hedefe git (home'a göre irtifa)."""
        self.master.mav.set_position_target_global_int_send(
            0, self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            0b0000111111111000,   # sadece pozisyon
            int(lat * 1e7), int(lon * 1e7), alt_rel,
            0, 0, 0, 0, 0, 0, 0, 0)

    def send_velocity_ned(self, vx: float, vy: float, vz: float, yaw_rate=0.0):
        """LOCAL_NED hız komutu (m/s). vx=Kuzey, vy=Doğu, vz=Aşağı(+).

        Güvenlik: hızlar config limitlerine kırpılır (drone düşmesin)."""
        vx = _clip(vx, CFG.pid.max_xy_speed_ms)
        vy = _clip(vy, CFG.pid.max_xy_speed_ms)
        vz = _clip(vz, CFG.pid.max_z_speed_ms)
        # type_mask: pos+accel ignore, vx/vy/vz aktif, yaw absolute IGNORE,
        # yaw_rate aktif (yaw_rate=0 ise onu da ignore).
        # Bit layout: [yaw_rate, yaw, force, az, ay, ax, vz, vy, vx, z, y, x]
        IGNORE_POS = 0b0000000000000111       # x, y, z (pos)
        IGNORE_ACC = 0b0000000111000000       # ax, ay, az
        IGNORE_FORCE = 0b0000001000000000     # force
        IGNORE_YAW = 0b0000010000000000       # yaw (CRITICAL — yoksa drone N'e döner)
        IGNORE_YAW_RATE = 0b0000100000000000  # yaw_rate
        type_mask = IGNORE_POS | IGNORE_ACC | IGNORE_FORCE | IGNORE_YAW
        if yaw_rate == 0.0:
            type_mask |= IGNORE_YAW_RATE
        self.master.mav.set_position_target_local_ned_send(
            0, self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            type_mask,
            0, 0, 0, vx, vy, vz, 0, 0, 0, 0, yaw_rate)

    def send_velocity_body(self, v_fwd: float, v_right: float, v_down: float,
                           yaw_rate: float = 0.0):
        """GÖVDE çerçevesinde hız komutu (m/s). Görsel servo için idealdir:
        v_fwd=ileri(burun), v_right=sağ, v_down=aşağı(+). Heading'e göre
        dönüşüm gerektirmez (MAV_FRAME_BODY_NED).

        Güvenlik: hızlar config limitlerine kırpılır (drone düşmesin)."""
        v_fwd = _clip(v_fwd, CFG.pid.max_xy_speed_ms)
        v_right = _clip(v_right, CFG.pid.max_xy_speed_ms)
        v_down = _clip(v_down, CFG.pid.max_z_speed_ms)
        type_mask = 0b0000011111000111  # sadece hız
        if yaw_rate == 0.0:
            type_mask |= 0b0000010000000000
        self.master.mav.set_position_target_local_ned_send(
            0, self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_FRAME_BODY_NED,
            type_mask,
            0, 0, 0, v_fwd, v_right, v_down, 0, 0, 0, 0, yaw_rate)

    def set_servo(self, channel: int, pwm: int, retries: int = 3,
                  ack_timeout: float = 0.5) -> bool:
        """AUX servo çıkışına PWM gönder + COMMAND_ACK doğrula.

        ArduCopter ACK'i COMMAND_ACK mesajı olarak gönderir; alınmazsa
        kritik failsafe (servo açılmadı = paket bırakılmadı varsay)."""
        for attempt in range(retries):
            self._command_long(mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
                               channel, pwm)
            ack = self.master.recv_match(
                type="COMMAND_ACK", blocking=True, timeout=ack_timeout)
            if (ack is not None
                    and ack.command == mavutil.mavlink.MAV_CMD_DO_SET_SERVO
                    and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED):
                print(f"[MAV] Servo {channel} -> {pwm} us (ACK ok)")
                return True
            print(f"[MAV] Servo ACK alınamadı (deneme {attempt + 1}/{retries})")
        return False

    def send_landing_target(self, angle_x: float, angle_y: float,
                            distance: float, time_usec: int = 0):
        """PRECLAND için: ArUco poz → LANDING_TARGET mesajı (10 Hz tavsiye).

        angle_x/y: marker'ın kamera optik eksenine göre açısal sapması (rad).
        distance: marker'a olan mutlak mesafe (m, lidar/aruco füzyonundan).
        ArduCopter PLND_TYPE=1 (MAVLink) iken yerleşik PID iniş yapar."""
        if time_usec == 0:
            time_usec = int(time.time() * 1e6)
        self.master.mav.landing_target_send(
            time_usec, 0,
            mavutil.mavlink.MAV_FRAME_BODY_FRD,
            angle_x, angle_y, distance,
            0, 0, 0, 0, 0, (0, 0, 0, 0), 0, 1)

    def setup_geofence(self, polygon: list[tuple[float, float]],
                       alt_max_m: float = 50.0,
                       radius_m: float = 200.0) -> bool:
        """ArduCopter geofence param + polygon yükle. RTL on breach.

        polygon: yarışma alanı köşe koordinatları (lat, lon). Boş list → sadece
        circle + alt fence (polygon olmadan da temel koruma sağlar)."""
        try:
            for name, val in [("FENCE_ENABLE", 1), ("FENCE_TYPE", 7),
                              ("FENCE_ACTION", 1),
                              ("FENCE_ALT_MAX", alt_max_m),
                              ("FENCE_RADIUS", radius_m)]:
                self.master.mav.param_set_send(
                    self.master.target_system,
                    self.master.target_component,
                    name.encode("ascii"), float(val),
                    mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
                time.sleep(0.05)
            if polygon:
                self.master.mav.mission_count_send(
                    self.master.target_system, self.master.target_component,
                    len(polygon), mavutil.mavlink.MAV_MISSION_TYPE_FENCE)
                for i, (lat, lon) in enumerate(polygon):
                    self.master.mav.mission_item_int_send(
                        self.master.target_system,
                        self.master.target_component,
                        i, mavutil.mavlink.MAV_FRAME_GLOBAL,
                        mavutil.mavlink.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION,
                        0, 0, len(polygon), 0, 0, 0,
                        int(lat * 1e7), int(lon * 1e7), 0,
                        mavutil.mavlink.MAV_MISSION_TYPE_FENCE)
                    time.sleep(0.05)
            print(f"[MAV] Geofence yüklendi (alt_max={alt_max_m}, "
                  f"radius={radius_m}, polygon={len(polygon)})")
            return True
        except Exception as e:
            print(f"[MAV] Geofence yükleme hatası: {e}")
            return False

    def force_disarm(self) -> bool:
        """Acil disarm (CRASH detection için). Force magic 21196 kullanır."""
        return self.disarm(timeout=2.0, force=True)

    def distance_to(self, lat: float, lon: float) -> float:
        t = self.telemetry()
        return haversine_m(t.lat, t.lon, lat, lon)


def _clip(v: float, limit: float) -> float:
    return max(-limit, min(limit, v))
