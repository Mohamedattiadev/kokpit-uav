"""
watchdog.py — systemd watchdog notifier.

sdnotify yoksa graceful skip. mission.py ana döngü her N saniyede notify()
çağırır; systemd WatchdogSec aşılırsa servisi yeniden başlatır.
"""
from __future__ import annotations
import time

try:
    import sdnotify  # type: ignore
    _HAS = True
except Exception:
    _HAS = False


class Watchdog:
    def __init__(self, period_s: float = 5.0):
        self.period_s = period_s
        self._last = 0.0
        self._notifier = None
        self.ready_sent = False
        if _HAS:
            self._notifier = sdnotify.SystemdNotifier()

    def ready(self) -> None:
        if self._notifier and not self.ready_sent:
            try:
                self._notifier.notify("READY=1")
            except Exception:
                pass
            self.ready_sent = True

    def notify(self) -> bool:
        """Çağırılmalı: her tick'te. period_s'den önce no-op (gürültü azalt)."""
        now = time.monotonic()
        if now - self._last < self.period_s:
            return False
        self._last = now
        if self._notifier:
            try:
                self._notifier.notify("WATCHDOG=1")
                return True
            except Exception:
                return False
        return False

    def stopping(self, reason: str = "") -> None:
        if self._notifier:
            try:
                self._notifier.notify(f"STOPPING=1\nSTATUS={reason}")
            except Exception:
                pass
