"""M8 — reboot recovery + READ_ONLY state geçişleri."""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from state_machine import MissionState, StateMachine, VALID_TRANSITIONS  # noqa: E402


def test_read_only_state_exists():
    assert hasattr(MissionState, "READ_ONLY")


def test_idle_to_read_only_allowed():
    assert MissionState.READ_ONLY in VALID_TRANSITIONS[MissionState.IDLE]


def test_read_only_can_go_disarm():
    fsm = StateMachine(initial=MissionState.IDLE)
    assert fsm.transition(MissionState.READ_ONLY)
    assert fsm.transition(MissionState.DISARM)


def test_setup_detects_mid_mission_reboot(monkeypatch):
    """drone.telemetry → armed + GUIDED → mission.fsm READ_ONLY."""
    from mission import Mission
    drone = MagicMock()
    drone.telemetry.return_value = MagicMock(armed=True, mode="GUIDED")
    drone.connect.return_value = None
    lora = MagicMock()
    cfg = MagicMock()
    # Bypass CFG.validate
    monkeypatch.setattr("mission.CFG.validate", lambda: [])

    m = Mission(drone=drone, lora=lora)
    # Stub setup'ı kısalt: verifier dataset / failsafe atla
    m.verifier = MagicMock()
    m.verifier.load_dataset.return_value = 0
    m._start_failsafe_monitor = lambda: None
    m.dropper = MagicMock()

    m.setup()
    assert m.fsm.state == MissionState.READ_ONLY


def test_setup_normal_armed_false(monkeypatch):
    from mission import Mission
    drone = MagicMock()
    drone.telemetry.return_value = MagicMock(armed=False, mode="STABILIZE")
    monkeypatch.setattr("mission.CFG.validate", lambda: [])
    m = Mission(drone=drone, lora=MagicMock())
    m.verifier = MagicMock()
    m.verifier.load_dataset.return_value = 0
    m._start_failsafe_monitor = lambda: None
    m.dropper = MagicMock()
    m.setup()
    assert m.fsm.state != MissionState.READ_ONLY
