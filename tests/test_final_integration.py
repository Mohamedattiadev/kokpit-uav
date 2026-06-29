"""N12 — Final integration: N1+N3+N4+N11 + happy path birlikte."""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "simulation" / "gazebo" / "scenarios"))

from preflight_check import PreflightCheck  # noqa: E402
from telemetry_recorder import TelemetryRecorder  # noqa: E402
from runs_index import build_index  # noqa: E402
from _common import FaultInjection, simulate  # noqa: E402

flask = pytest.importorskip("flask")
import replay_dashboard as rd  # noqa: E402


def _good_tel():
    return SimpleNamespace(
        lat=39.0, lon=32.0, alt_rel=10.0, vx=0.1, vy=0.0, vz=0.0,
        heading=0.0, roll=0.0, pitch=0.0, yaw=0.0,
        battery_voltage=24.0, battery_remaining=80,
        satellites=12, hdop=0.7, mode="GUIDED", armed=True,
        lidar_alt_body=9.5,
        fence_enable=1, fence_total=4,
        lidar_ok=True, lidar_last_update=time.time(),
        fix_type=3, ekf_ok=True,
    )


def test_step_1_preflight_passes_with_mocks():
    pf = PreflightCheck(
        telemetry_provider=_good_tel,
        camera_fps_provider=lambda: 30.0,
        lora_age_provider=lambda: 0.5,
        face_dataset_count=lambda: 3,
        trt_ready=lambda: True,
        systemd_status=lambda: True,
        require_systemd=True,
    )
    r = pf.run()
    assert r.passed, [(x.name, x.msg) for x in r.results if not x.passed]


def test_step_2_recorder_writes_during_mission(tmp_path):
    run_dir = tmp_path / "run01"
    run_dir.mkdir()
    rec = TelemetryRecorder(_good_tel, out_path=run_dir / "telemetry.csv",
                            rate_hz=0.01)
    rec.start()
    for _ in range(3):
        rec.write_once()
    rec.close()
    assert (run_dir / "telemetry.csv").exists()
    assert len((run_dir / "telemetry.csv").read_text().splitlines()) >= 4


def test_step_3_happy_scenario_delivers():
    o = simulate(FaultInjection())
    assert o.package_delivered


def test_step_4_index_updated_after_run(tmp_path):
    run_dir = tmp_path / "20260629_120000"
    run_dir.mkdir()
    (run_dir / "events.jsonl").write_text(
        json.dumps({"ts": 1000, "event": "start"}) + "\n" +
        json.dumps({"ts": 1120, "event": "package_delivered"}) + "\n"
    )
    (run_dir / "telemetry.csv").write_text("h\n" + "x\n" * 10)
    idx = build_index(tmp_path)
    assert len(idx["runs"]) == 1
    assert idx["runs"][0]["package_delivered"]
    assert idx["runs"][0]["telemetry_rows"] == 10


def test_step_5_replay_dashboard_200(tmp_path, monkeypatch):
    (tmp_path / "20260629_120000").mkdir()
    monkeypatch.setattr(rd, "RUNS_DIR", tmp_path)
    rd.app.testing = True
    c = rd.app.test_client()
    r = c.get("/")
    assert r.status_code == 200
    assert b"20260629_120000" in r.data
    r2 = c.get("/api/runs")
    assert r2.status_code == 200
    assert "20260629_120000" in r2.get_json()["runs"]
