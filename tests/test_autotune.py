"""N7 — autotune orchestrator state machine."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from autotune import AutoTuneOrchestrator, TuneContext, TuneState  # noqa: E402


def _good_ctx(statustext=None):
    msgs = list(statustext or [])
    return TuneContext(
        set_mode=lambda m: True,
        set_param=lambda k, v: True,
        save_param=lambda: True,
        statustext_iter=lambda: msgs,
        disarm=lambda: True,
    )


def test_happy_path_reaches_land():
    ctx = _good_ctx(statustext=["AutoTune: success"])
    orch = AutoTuneOrchestrator(ctx)
    end = orch.run()
    assert end == TuneState.LAND_DONE


def test_mode_set_failure():
    ctx = TuneContext(
        set_mode=lambda m: False,
        set_param=lambda k, v: True, save_param=lambda: True,
        statustext_iter=lambda: [], disarm=lambda: True,
    )
    orch = AutoTuneOrchestrator(ctx)
    end = orch.run()
    assert end == TuneState.FAILED
    assert "LOITER" in (orch.error or "")


def test_autotune_fail_message():
    ctx = _good_ctx(statustext=["AutoTune: failure"])
    orch = AutoTuneOrchestrator(ctx)
    end = orch.run()
    assert end == TuneState.FAILED


def test_save_failure():
    ctx = TuneContext(
        set_mode=lambda m: True,
        set_param=lambda k, v: True,
        save_param=lambda: False,
        statustext_iter=lambda: ["AutoTune: success"],
        disarm=lambda: True,
    )
    orch = AutoTuneOrchestrator(ctx)
    end = orch.run()
    assert end == TuneState.FAILED
    assert "save" in (orch.error or "")
