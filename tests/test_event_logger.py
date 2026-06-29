"""Event logger + mission integration testleri."""
from __future__ import annotations
import json
from pathlib import Path

import event_logger as evl


def test_emit_appends_jsonl(tmp_path):
    p = tmp_path / "events.jsonl"
    lg = evl.EventLogger(p)
    lg.emit("start")
    lg.emit("package_delivered", recipient_id=7)
    lg.close()
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "start" and "ts" in first
    second = json.loads(lines[1])
    assert second["recipient_id"] == 7


def test_global_emit_silent_without_global():
    evl.set_global(None)
    evl.emit("noop")  # no exception


def test_global_emit_writes(tmp_path):
    p = tmp_path / "events.jsonl"
    lg = evl.EventLogger(p)
    evl.set_global(lg)
    try:
        evl.emit("phase", state="TAKEOFF")
    finally:
        lg.close()
        evl.set_global(None)
    data = json.loads(p.read_text().strip())
    assert data["state"] == "TAKEOFF"


def test_make_run_dir_unique(tmp_path):
    d = evl.make_run_dir(tmp_path)
    assert d.exists() and d.parent == tmp_path
    assert d.name[:8].isdigit()


def test_fsm_transition_emits_phase(tmp_path):
    from state_machine import StateMachine, MissionState
    p = tmp_path / "events.jsonl"
    lg = evl.EventLogger(p)
    evl.set_global(lg)
    sm = StateMachine()
    try:
        sm.transition(MissionState.WAIT_PACKET)
        sm.transition(MissionState.PREFLIGHT, force=True)
    finally:
        lg.close()
        evl.set_global(None)
    lines = [json.loads(x) for x in p.read_text().strip().splitlines()]
    phases = [ln for ln in lines if ln["event"] == "phase"]
    assert len(phases) == 2
    assert phases[1]["state"] == "PREFLIGHT"
