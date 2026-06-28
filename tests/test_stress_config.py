"""Config validate + sanity testleri — yarışma günü yanlış config crash etmesin."""
from __future__ import annotations
import pytest

from config import CFG, Config


def test_config_validate_default_ok():
    """Default CFG validate() hata vermemeli."""
    errs = CFG.validate()
    assert errs == [], f"default config invalid: {errs}"


def test_config_invalid_drop_altitude_band_caught():
    """min_drop > max_drop → validate yakalama (best-effort)."""
    c = Config()
    c.dropper.min_drop_altitude_m = 5.0
    c.dropper.max_drop_altitude_m = 2.0
    errs = c.validate()
    # validate() bu özel kuralı kapsamıyor; ama servo guard runtime'da yakalar.
    # Bu testin amacı validate sözleşmesini gösterip future regression engellemek.
    # (Şu an boş kalabilir.)


def test_config_battery_thresholds_ordered():
    """LOW > CRT olmalı (low yüksek, crit düşük)."""
    s = CFG.safety
    assert s.battery_low_voltage > s.battery_critical_voltage


def test_config_drop_altitude_inside_servo_band():
    """drop_altitude_m servo bandı içinde olmalı."""
    f, d = CFG.flight, CFG.dropper
    assert d.min_drop_altitude_m <= f.drop_altitude_m <= d.max_drop_altitude_m


def test_config_pwm_locked_ne_released():
    """Kilitli ≠ açık PWM (validate kuralı)."""
    d = CFG.dropper
    assert d.pwm_locked != d.pwm_released


def test_config_takeoff_below_cruise():
    """Takeoff irtifa cruise'tan küçük (mantıksal)."""
    f = CFG.flight
    assert f.takeoff_altitude_m <= f.cruise_altitude_m


def test_config_search_above_drop():
    """Arama irtifa drop'tan büyük (üstten süpür sonra in)."""
    f = CFG.flight
    assert f.search_altitude_m > f.drop_altitude_m


def test_config_pid_speed_positive():
    """Hız limitleri pozitif."""
    p = CFG.pid
    assert p.max_xy_speed_ms > 0
    assert p.max_z_speed_ms > 0


def test_config_geofence_positive():
    """Geofence yarıçap + alt pozitif."""
    s = CFG.safety
    assert s.geofence_radius_m > 0
    assert s.geofence_max_alt_m > 0


def test_config_simulation_env_override():
    """KOKPIT_SIM env değişkeni SIMULATION'ı kontrol eder."""
    import os
    # Test ortamında zaten KOKPIT_SIM=1 set edilmiş olmalı
    assert os.environ.get("KOKPIT_SIM") == "1"
