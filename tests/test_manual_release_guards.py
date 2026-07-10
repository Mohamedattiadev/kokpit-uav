"""package_dropper.manual_release() — faz/yüz/marker guard'larını atlar ama
irtifa+eğim guard'ları korunur (fiziksel güvenlik atlanamaz)."""
from __future__ import annotations
from unittest.mock import MagicMock

from config import CFG
from package_dropper import PackageDropper


def _drone(alt, roll=0.0, pitch=0.0, lidar_ok=True):
    drone = MagicMock()
    drone.telemetry.return_value = MagicMock(
        lidar_alt=alt, alt_rel=alt, lidar_ok=lidar_ok, roll=roll, pitch=pitch)
    drone.set_servo.return_value = True
    return drone


def test_manual_release_ignores_phase_face_marker_guards():
    mid_alt = (CFG.dropper.min_drop_altitude_m + CFG.dropper.max_drop_altitude_m) / 2
    d = PackageDropper(_drone(mid_alt))
    assert d.manual_release() is True
    assert d.dropped is True


def test_manual_release_still_blocked_outside_altitude_band():
    d = PackageDropper(_drone(CFG.dropper.max_drop_altitude_m + 5))
    assert d.manual_release() is False
    assert d.dropped is False


def test_manual_release_still_blocked_on_extreme_tilt():
    mid_alt = (CFG.dropper.min_drop_altitude_m + CFG.dropper.max_drop_altitude_m) / 2
    d = PackageDropper(_drone(mid_alt, roll=0.6))  # ~34° > 15°
    assert d.manual_release() is False


def test_manual_release_idempotent():
    mid_alt = (CFG.dropper.min_drop_altitude_m + CFG.dropper.max_drop_altitude_m) / 2
    d = PackageDropper(_drone(mid_alt))
    assert d.manual_release() is True
    assert d.manual_release() is True   # zaten bırakılmış -> True, tekrar servo çağrılmaz
    assert d.drone.set_servo.call_count == 1
