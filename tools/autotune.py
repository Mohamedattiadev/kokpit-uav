"""N7 — Headless AutoTune orchestrator (rapor 4.3 saha tuning).

Manuel pilot kontrolü ZORUNLU. Bu script sadece orkestrasyon:
LOITER -> AUTOTUNE_AXES set -> ALT_HOLD + AUTOTUNE channel -> bekle -> SAVE.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional


class TuneState(Enum):
    INIT = auto()
    LOITER_SET = auto()
    AXES_SET = auto()
    ALT_HOLD_SET = auto()
    TUNING = auto()
    SUCCESS = auto()
    SAVED = auto()
    LAND_DONE = auto()
    FAILED = auto()


@dataclass
class TuneContext:
    set_mode: Callable[[str], bool]
    set_param: Callable[[str, int], bool]
    save_param: Callable[[], bool]
    statustext_iter: Callable[[], list]   # son mesajlar
    disarm: Callable[[], bool]
    axes: int = 7   # roll+pitch+yaw


class AutoTuneOrchestrator:
    def __init__(self, ctx: TuneContext):
        self.ctx = ctx
        self.state = TuneState.INIT
        self.error: Optional[str] = None

    def step(self) -> TuneState:
        try:
            if self.state == TuneState.INIT:
                if self.ctx.set_mode("LOITER"):
                    self.state = TuneState.LOITER_SET
                else:
                    self._fail("LOITER set failed")
            elif self.state == TuneState.LOITER_SET:
                if self.ctx.set_param("AUTOTUNE_AXES", self.ctx.axes):
                    self.state = TuneState.AXES_SET
                else:
                    self._fail("AUTOTUNE_AXES set failed")
            elif self.state == TuneState.AXES_SET:
                if self.ctx.set_mode("ALT_HOLD"):
                    self.state = TuneState.ALT_HOLD_SET
                else:
                    self._fail("ALT_HOLD set failed")
            elif self.state == TuneState.ALT_HOLD_SET:
                self.state = TuneState.TUNING
            elif self.state == TuneState.TUNING:
                msgs = self.ctx.statustext_iter()
                if any("AutoTune: success" in m for m in msgs):
                    self.state = TuneState.SUCCESS
                elif any("autotune: fail" in m.lower() for m in msgs):
                    self._fail("AutoTune fail mesajı geldi")
            elif self.state == TuneState.SUCCESS:
                if self.ctx.save_param():
                    self.state = TuneState.SAVED
                else:
                    self._fail("save failed")
            elif self.state == TuneState.SAVED:
                self.ctx.set_mode("RTL")
                self.ctx.disarm()
                self.state = TuneState.LAND_DONE
        except Exception as e:
            self._fail(f"exc: {e}")
        return self.state

    def _fail(self, why: str):
        self.error = why
        self.state = TuneState.FAILED

    def run(self, max_iters: int = 1000) -> TuneState:
        for _ in range(max_iters):
            prev = self.state
            self.step()
            if self.state in (TuneState.LAND_DONE, TuneState.FAILED):
                return self.state
            if self.state == prev and self.state == TuneState.TUNING:
                # pilot AutoTune complete sinyalini bekle — caller döngüsü
                return self.state
        return self.state
