"""N4 — Telemetry recorder (forensic CSV).

Her 1 Hz state snapshot — crash sebebi tespiti için (rapor 3.3.3).
Mission.setup() başlatır, Mission.close() durdurur.
"""
from __future__ import annotations
import csv
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

HEADER = [
    "ts_unix_us", "lat", "lon", "alt_rel", "vx", "vy", "vz", "heading",
    "roll", "pitch", "yaw", "battery_v", "battery_pct", "satellites", "hdop",
    "mode", "armed", "lidar_alt_body", "mission_state", "failsafe_active",
]


class TelemetryRecorder:
    def __init__(self, telemetry_provider: Callable,
                 mission_state_provider: Optional[Callable] = None,
                 failsafe_provider: Optional[Callable] = None,
                 out_path: Optional[Path] = None,
                 rate_hz: float = 1.0):
        self.tel = telemetry_provider
        self.state = mission_state_provider or (lambda: "")
        self.failsafe = failsafe_provider or (lambda: False)
        if out_path is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            out_path = Path("runs") / ts / "telemetry.csv"
        self.out_path = Path(out_path)
        self.period = 1.0 / max(0.1, rate_hz)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fp = None
        self._writer: Optional[csv.writer] = None
        self.rows_written = 0

    def start(self):
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.out_path.open("w", newline="")
        self._writer = csv.writer(self._fp)
        self._writer.writerow(HEADER)
        self._fp.flush()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _row(self) -> list:
        t = self.tel()
        return [
            int(time.time() * 1e6),
            getattr(t, "lat", 0.0), getattr(t, "lon", 0.0),
            getattr(t, "alt_rel", 0.0),
            getattr(t, "vx", 0.0), getattr(t, "vy", 0.0), getattr(t, "vz", 0.0),
            getattr(t, "heading", 0.0),
            getattr(t, "roll", 0.0), getattr(t, "pitch", 0.0), getattr(t, "yaw", 0.0),
            getattr(t, "battery_voltage", 0.0),
            getattr(t, "battery_remaining", 0.0),
            getattr(t, "satellites", 0),
            getattr(t, "hdop", 0.0),
            getattr(t, "mode", ""),
            int(bool(getattr(t, "armed", False))),
            getattr(t, "lidar_alt_body", 0.0),
            self.state(),
            int(bool(self.failsafe())),
        ]

    def write_once(self):
        """Test desteği: tek satır yaz (loop'a girmeden)."""
        if self._writer is None:
            raise RuntimeError("recorder.start() çağrılmadı")
        self._writer.writerow(self._row())
        self._fp.flush()
        self.rows_written += 1

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.write_once()
            except Exception as e:
                print(f"[TEL_REC] yazma hatası: {e}")
            self._stop.wait(self.period)

    def close(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._fp:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None
