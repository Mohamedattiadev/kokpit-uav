"""Durum makinesi testleri — geçişler ve terminal durumlar."""
from state_machine import StateMachine, MissionState, VALID_TRANSITIONS


def test_nominal_flow_transitions_valid():
    flow = [
        MissionState.WAIT_PACKET, MissionState.PREFLIGHT, MissionState.TAKEOFF,
        MissionState.NAVIGATE, MissionState.SEARCH_MARKER,
        MissionState.PRECISION_APPROACH, MissionState.BIOMETRIC_VERIFY,
        MissionState.DROP_PACKAGE, MissionState.RETURN_HOME,
        MissionState.LANDING, MissionState.DISARM, MissionState.MISSION_COMPLETE,
    ]
    sm = StateMachine(logger=lambda *a: None)
    prev = sm.state
    for nxt in flow:
        assert nxt in VALID_TRANSITIONS[prev], f"{prev}->{nxt} geçersiz"
        sm.transition(nxt)
        prev = nxt
    assert sm.is_terminal()


def test_abort_reachable_from_flight_states():
    for st in [MissionState.TAKEOFF, MissionState.NAVIGATE,
               MissionState.PRECISION_APPROACH, MissionState.BIOMETRIC_VERIFY]:
        assert MissionState.ABORT in VALID_TRANSITIONS[st]


def test_biometric_fail_returns_home():
    # Yüz eşleşmezse DROP yerine RETURN_HOME mümkün olmalı
    assert MissionState.RETURN_HOME in VALID_TRANSITIONS[MissionState.BIOMETRIC_VERIFY]


def test_terminal_states_have_no_exit():
    assert VALID_TRANSITIONS[MissionState.MISSION_COMPLETE] == set()
    assert VALID_TRANSITIONS[MissionState.FAILED] == set()


def test_history_recorded():
    sm = StateMachine(logger=lambda *a: None)
    sm.transition(MissionState.WAIT_PACKET)
    sm.transition(MissionState.PREFLIGHT)
    assert len(sm.history) == 3  # IDLE + 2
