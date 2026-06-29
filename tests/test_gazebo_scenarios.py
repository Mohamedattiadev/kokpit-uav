"""N2 — Gazebo senaryo davranış testleri (sim-only, gz binary olmadan)."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "simulation" / "gazebo" / "scenarios"))

from _common import FaultInjection, simulate  # noqa: E402


def test_01_happy_path():
    o = simulate(FaultInjection())
    assert o.package_delivered
    assert not o.rtl_triggered and not o.land_triggered


def test_02_marker_lost_aborts():
    o = simulate(FaultInjection(marker_visible=False))
    assert not o.package_delivered
    assert o.abort_reason == "MARKER_LOST"


def test_03_face_mismatch_rtl():
    o = simulate(FaultInjection(face_match=False))
    assert o.rtl_triggered
    assert o.abort_reason == "FACE_MISMATCH"


def test_04_link_lost_rtl():
    o = simulate(FaultInjection(link_alive=False))
    assert o.rtl_triggered
    assert o.abort_reason == "LINK_LOST"


def test_05_battery_low_rtl():
    o = simulate(FaultInjection(battery_voltage=21.0))
    assert o.rtl_triggered
    assert o.abort_reason == "BATTERY_LOW"


def test_06_gps_lost_land():
    o = simulate(FaultInjection(gps_fix_type=1, gps_sats=3))
    assert o.land_triggered
    assert o.abort_reason == "GPS_LOST"


def test_scenario_runner_script_exists():
    p = ROOT / "simulation" / "gazebo" / "run_scenarios.sh"
    assert p.exists() and p.is_file()


def test_world_sdf_exists():
    p = ROOT / "simulation" / "gazebo" / "world" / "kokpit_arena.sdf"
    assert p.exists()
    assert "kokpit_arena" in p.read_text()
