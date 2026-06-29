"""Event logger — runs/<ts>/events.jsonl JSONL writer.

Mission lifecycle olaylarını (start, takeoff, marker_locked, face_match,
package_delivered, abort, phase, rtl_complete) zaman damgalı yazar.
Replay dashboard bu dosyayı okur. Rapor 3.3.3 uçuş kaydı.
"""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path
from typing import Optional


class EventLogger:
    def __init__(self, out_path: Path):
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.out_path.open("a", buffering=1)
        self._lock = threading.Lock()
        self.events_emitted = 0

    def emit(self, event: str, **payload) -> None:
        rec = {"ts": time.time(), "event": event, **payload}
        line = json.dumps(rec, default=str)
        with self._lock:
            self._fp.write(line + "\n")
            self._fp.flush()
        self.events_emitted += 1

    def close(self) -> None:
        with self._lock:
            try:
                self._fp.close()
            except Exception:
                pass


_GLOBAL: Optional[EventLogger] = None


def get() -> Optional[EventLogger]:
    return _GLOBAL


def set_global(logger: Optional[EventLogger]) -> None:
    global _GLOBAL
    _GLOBAL = logger


def emit(event: str, **payload) -> None:
    """Modül seviyesi shortcut — global logger varsa yazar, yoksa sessiz."""
    lg = _GLOBAL
    if lg is not None:
        try:
            lg.emit(event, **payload)
        except Exception as e:
            print(f"[EVENT] yazma hatası: {e}")


def make_run_dir(base: Optional[Path] = None) -> Path:
    """runs/<YYYYmmdd_HHMMSS>/ oluştur ve döndür."""
    base = base or Path("runs")
    ts = time.strftime("%Y%m%d_%H%M%S")
    d = Path(base) / ts
    d.mkdir(parents=True, exist_ok=True)
    return d
