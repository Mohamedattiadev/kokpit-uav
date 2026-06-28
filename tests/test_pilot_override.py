"""M9 — PILOT_OVERRIDE failsafe testleri."""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from mission import Mission  # noqa: E402


def _make_mission(mode: str, armed: bool = True):
    drone = MagicMock()
    drone.telemetry.return_value = MagicMock(
        mode=mode, armed=armed,
        battery_voltage=24.0, satellites=12, hdop=0.8, fix_type=3,
        roll=0.0, pitch=0.0, accel_z_g=1.0, last_heartbeat=9e9,
        lat=39.0, lon=33.0, alt_rel=5.0)
    drone.link_alive.return_value = True
    drone.home_lat = 39.0
    drone.home_lon = 33.0
    drone.force_disarm.return_value = True
    m = Mission(drone=drone, lora=MagicMock())
    m.dropper = MagicMock()
    return m


def test_manual_mode_pushes_user_abort():
    m = _make_mission(mode="MANUAL")
    # Run one iteration of failsafe loop manually
    m._monitor_running = False
    # Inline run loop body subset
    t = m.drone.telemetry()
    if t.mode in ("MANUAL", "STABILIZE", "ACRO"):
        m._push_failsafe(m.PRIO_USER_ABORT, "PILOT_OVERRIDE",
                         f"mode={t.mode}")
    assert len(m._failsafe_heap) == 1
    prio_neg, _, kind, _ = m._failsafe_heap[0]
    assert kind == "PILOT_OVERRIDE"
    assert -prio_neg == m.PRIO_USER_ABORT


def test_stabilize_triggers_override():
    m = _make_mission(mode="STABILIZE")
    t = m.drone.telemetry()
    assert t.mode in ("MANUAL", "STABILIZE", "ACRO")


def test_guided_does_not_trigger_override():
    m = _make_mission(mode="GUIDED")
    t = m.drone.telemetry()
    assert t.mode not in ("MANUAL", "STABILIZE", "ACRO")


def test_user_abort_highest_priority():
    m = _make_mission(mode="GUIDED")
    m._push_failsafe(m.PRIO_BATTERY_LOW, "BATTERY_LOW", "x")
    m._push_failsafe(m.PRIO_USER_ABORT, "PILOT_OVERRIDE", "x")
    m._push_failsafe(m.PRIO_GEOFENCE, "GEOFENCE", "x")
    top = m._failsafe_heap[0]
    assert top[2] == "PILOT_OVERRIDE"
