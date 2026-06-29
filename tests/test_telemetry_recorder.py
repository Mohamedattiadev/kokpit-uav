"""N4 — telemetry_recorder testleri."""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace

from telemetry_recorder import TelemetryRecorder, HEADER


def _tel():
    return SimpleNamespace(
        lat=39.0, lon=32.0, alt_rel=10.0, vx=1.0, vy=0.0, vz=0.0,
        heading=90.0, roll=0.0, pitch=0.0, yaw=1.57,
        battery_voltage=24.0, battery_remaining=80,
        satellites=12, hdop=0.7, mode="GUIDED", armed=True,
        lidar_alt_body=9.5,
    )


def test_header_written(tmp_path):
    p = tmp_path / "tel.csv"
    rec = TelemetryRecorder(_tel, out_path=p)
    rec.start()
    rec.close()
    line0 = p.read_text().splitlines()[0]
    assert line0.split(",") == HEADER


def test_write_row_appends(tmp_path):
    p = tmp_path / "tel.csv"
    rec = TelemetryRecorder(_tel, out_path=p, rate_hz=0.01)
    rec.start()
    rec.write_once()
    rec.write_once()
    rec.close()
    lines = p.read_text().splitlines()
    assert len(lines) >= 3  # header + en az 2 data
    assert any("GUIDED" in ln for ln in lines[1:])


def test_close_graceful_without_thread(tmp_path):
    p = tmp_path / "tel.csv"
    rec = TelemetryRecorder(_tel, out_path=p)
    rec.start()
    rec.close()
    rec.close()  # idempotent


def test_failsafe_flag_recorded(tmp_path):
    p = tmp_path / "tel.csv"
    rec = TelemetryRecorder(
        _tel, mission_state_provider=lambda: "DELIVERY",
        failsafe_provider=lambda: True, out_path=p,
    )
    rec.start()
    rec.write_once()
    rec.close()
    last = p.read_text().splitlines()[-1]
    assert last.split(",")[-1] == "1"
    assert "DELIVERY" in last
