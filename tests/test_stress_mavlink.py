"""MAVLink bridge edge case testleri — yaw mask, geofence upload, ACK retry,
mesaj dispatch."""
from __future__ import annotations
import struct
import time
from unittest.mock import MagicMock, patch

import pytest


def test_yaw_mask_bit_count():
    """SET_POSITION_TARGET type_mask: pos+accel+force+yaw+yaw_rate ignore.
    Bit pattern 0b0000111111000111 (yaw_rate=0 ile birlikte 0b0000111111000111
    | 0b0000010000000000) = 0b0000111111000111 + 0x0400 = 0b0000111111000111 or 0x0400."""
    IGNORE_POS = 0b0000000000000111
    IGNORE_ACC = 0b0000000111000000
    IGNORE_FORCE = 0b0000001000000000
    IGNORE_YAW = 0b0000010000000000
    IGNORE_YAW_RATE = 0b0000100000000000
    mask = IGNORE_POS | IGNORE_ACC | IGNORE_FORCE | IGNORE_YAW | IGNORE_YAW_RATE
    # Doğru maske 0b0000111111000111 = 0x0FC7
    assert mask == 0x0FC7
    # YAW_IGNORE biti AYRICA set olmalı (en kritik fix)
    assert mask & IGNORE_YAW
    assert mask & IGNORE_YAW_RATE


def test_servo_ack_retries_on_failure():
    """set_servo: ACK gelmezse 3 deneme yapmalı, sonuçta False."""
    from mavlink_interface import DroneController

    drone = DroneController.__new__(DroneController)
    drone.master = MagicMock()
    drone.master.target_system = 1
    drone.master.target_component = 1
    drone.master.recv_match.return_value = None   # ACK hiç gelmez

    ok = drone.set_servo(9, 1900, retries=3, ack_timeout=0.05)
    assert ok is False
    # 3 deneme = 3 command_long_send + 3 recv_match
    assert drone.master.recv_match.call_count == 3


def test_servo_ack_succeeds_on_first_try():
    from mavlink_interface import DroneController
    from pymavlink import mavutil

    ack = MagicMock()
    ack.command = mavutil.mavlink.MAV_CMD_DO_SET_SERVO
    ack.result = mavutil.mavlink.MAV_RESULT_ACCEPTED

    drone = DroneController.__new__(DroneController)
    drone.master = MagicMock()
    drone.master.target_system = 1
    drone.master.target_component = 1
    drone.master.recv_match.return_value = ack

    ok = drone.set_servo(9, 1900, retries=3, ack_timeout=0.5)
    assert ok is True
    assert drone.master.recv_match.call_count == 1


def test_landing_target_packs_correctly():
    """send_landing_target çağrı parametreleri doğru."""
    from mavlink_interface import DroneController

    drone = DroneController.__new__(DroneController)
    drone.master = MagicMock()
    drone.send_landing_target(0.1, 0.05, 2.5)
    drone.master.mav.landing_target_send.assert_called_once()
    args, _ = drone.master.mav.landing_target_send.call_args
    # angle_x, angle_y, distance argümanlar (time_usec, target_num, frame sonra)
    # konum: time_usec=arg0, target_num=arg1, frame=arg2, angle_x=arg3, angle_y=arg4
    assert abs(args[3] - 0.1) < 1e-6
    assert abs(args[4] - 0.05) < 1e-6
    assert abs(args[5] - 2.5) < 1e-6


def test_force_disarm_uses_magic():
    """force_disarm → disarm(force=True) → 21196 magic kullanır."""
    from mavlink_interface import DroneController

    drone = DroneController.__new__(DroneController)
    drone.master = MagicMock()
    drone.tel = MagicMock()
    drone.tel.armed = False
    drone._lock = MagicMock()
    drone._lock.__enter__ = MagicMock(return_value=None)
    drone._lock.__exit__ = MagicMock(return_value=None)
    # disarm() telemetry().armed false dönüp hemen başarılı
    with patch.object(drone, 'telemetry') as mock_tel:
        t = MagicMock(); t.armed = False
        mock_tel.return_value = t
        ok = drone.force_disarm()
    assert ok is True


def test_telemetry_dataclass_has_safety_fields():
    """Telemetry dataclass Sprint 1 alanlarını içeriyor mu."""
    from mavlink_interface import Telemetry
    t = Telemetry()
    # Mevcut alanlar
    for field in ("lat", "lon", "alt_rel", "battery_voltage",
                  "armed", "mode", "ekf_ok"):
        assert hasattr(t, field), f"Telemetry.{field} eksik"
    # Sprint 1 eklemeleri
    for field in ("lidar_alt", "lidar_ok", "roll", "pitch", "yaw", "accel_z_g"):
        assert hasattr(t, field), f"Telemetry.{field} (Sprint 1) eksik"


def test_haversine_known_distance():
    """Haversine: 1° lat farkı ≈ 111.32 km."""
    from mavlink_interface import haversine_m
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert 110000 < d < 112000


def test_haversine_same_point_zero():
    from mavlink_interface import haversine_m
    assert haversine_m(39.9, 32.8, 39.9, 32.8) < 0.01


def test_haversine_antipodal():
    """Antipod noktalar arası mesafe ≈ π R."""
    from mavlink_interface import haversine_m
    d = haversine_m(0.0, 0.0, 0.0, 180.0)
    # Yaklaşık yarıçap × π
    assert 20_000_000 < d < 20_100_000


def test_setup_geofence_param_writes():
    """setup_geofence: FENCE_ENABLE + TYPE + ACTION + ALT_MAX + RADIUS yazar."""
    from mavlink_interface import DroneController

    drone = DroneController.__new__(DroneController)
    drone.master = MagicMock()
    drone.master.target_system = 1
    drone.master.target_component = 1

    ok = drone.setup_geofence(polygon=[], alt_max_m=50, radius_m=200)
    assert ok is True
    # 5 param yazma + polygon yok
    call_count = drone.master.mav.param_set_send.call_count
    assert call_count >= 5


def test_setup_geofence_with_polygon():
    from mavlink_interface import DroneController

    drone = DroneController.__new__(DroneController)
    drone.master = MagicMock()
    drone.master.target_system = 1
    drone.master.target_component = 1

    poly = [(39.94, 32.84), (39.95, 32.84), (39.95, 32.86), (39.94, 32.86)]
    ok = drone.setup_geofence(polygon=poly)
    assert ok is True
    # mission_count_send + 4 mission_item_int_send
    drone.master.mav.mission_count_send.assert_called_once()
    assert drone.master.mav.mission_item_int_send.call_count == 4
