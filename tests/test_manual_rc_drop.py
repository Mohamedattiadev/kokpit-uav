"""Kumanda (RC) manuel paket bırakma — RC6 switch, edge-triggered.

Pilot RC6'yı >=manual_rc_pwm_threshold'a alırsa FSM fazından bağımsız
dropper.manual_release() tetiklenir; irtifa/eğim guard'ları hâlâ geçerlidir
(package_dropper.drop() üzerinden).
"""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock

from config import CFG
from mission import Mission


def _tel(pwm: int | None):
    rc = {} if pwm is None else {CFG.dropper.manual_rc_channel: pwm}
    return SimpleNamespace(rc_channels=rc)


def _make_mission():
    m = Mission(drone=MagicMock(), lora=MagicMock())
    m.dropper = MagicMock()
    m.dropper.dropped = False
    return m


def test_switch_above_threshold_triggers_manual_release():
    m = _make_mission()
    m._check_manual_rc_drop(_tel(1800))
    m.dropper.manual_release.assert_called_once()


def test_switch_below_threshold_does_nothing():
    m = _make_mission()
    m._check_manual_rc_drop(_tel(1000))
    m.dropper.manual_release.assert_not_called()


def test_edge_triggered_only_fires_once_while_held():
    m = _make_mission()
    m._check_manual_rc_drop(_tel(1800))
    m._check_manual_rc_drop(_tel(1800))
    m._check_manual_rc_drop(_tel(1800))
    m.dropper.manual_release.assert_called_once()


def test_refires_after_switch_cycled():
    m = _make_mission()
    m._check_manual_rc_drop(_tel(1800))
    m._check_manual_rc_drop(_tel(1000))
    m._check_manual_rc_drop(_tel(1800))
    assert m.dropper.manual_release.call_count == 2


def test_no_channel_data_is_noop():
    m = _make_mission()
    m._check_manual_rc_drop(_tel(None))
    m.dropper.manual_release.assert_not_called()


def test_already_dropped_does_not_refire():
    m = _make_mission()
    m.dropper.dropped = True
    m._check_manual_rc_drop(_tel(1800))
    m.dropper.manual_release.assert_not_called()
