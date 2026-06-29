"""#1+#3+#5 — track/phases/failsafe JSON endpoint testleri."""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

flask = pytest.importorskip("flask")
import replay_dashboard as rd


CSV_HEADER = ("ts_unix_us,lat,lon,alt_rel,vx,vy,vz,heading,roll,pitch,yaw,"
              "battery_v,battery_pct,satellites,hdop,mode,armed,lidar_alt_body,"
              "mission_state,failsafe_active")


def _make_run(d: Path, rows):
    d.mkdir(parents=True, exist_ok=True)
    (d / "telemetry.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "RUNS_DIR", tmp_path)
    rd.app.testing = True
    return rd.app.test_client(), tmp_path


def test_track_json_returns_points(client):
    c, td = client
    _make_run(td / "r1", [
        "1000000000,39.92,32.85,0,0,0,0,0,0,0,0,24,90,12,0.7,GUIDED,1,0,IDLE,0",
        "1010000000,39.921,32.851,5,0,0,1,0,0,0,0,24,89,12,0.7,GUIDED,1,5,TAKEOFF,0",
    ])
    r = c.get("/run/r1/track.json")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["points"]) == 2
    assert abs(data["points"][0]["lat"] - 39.92) < 1e-6


def test_track_skips_zero_fill(client):
    c, td = client
    _make_run(td / "r1", [
        "1000000000,0.0,0.0,0,0,0,0,0,0,0,0,24,90,12,0.7,GUIDED,1,0,IDLE,0",
        "1010000000,39.92,32.85,5,0,0,1,0,0,0,0,24,89,12,0.7,GUIDED,1,5,TAKEOFF,0",
    ])
    data = c.get("/run/r1/track.json").get_json()
    assert len(data["points"]) == 1


def test_phases_collapses_consecutive(client):
    c, td = client
    _make_run(td / "r1", [
        "1000000000,39,32,0,0,0,0,0,0,0,0,24,90,12,0.7,GUIDED,1,0,IDLE,0",
        "1005000000,39,32,0,0,0,0,0,0,0,0,24,90,12,0.7,GUIDED,1,0,IDLE,0",
        "1010000000,39,32,5,0,0,1,0,0,0,0,24,89,12,0.7,GUIDED,1,5,TAKEOFF,0",
        "1020000000,39,32,10,0,0,0,0,0,0,0,24,88,12,0.7,GUIDED,1,10,NAVIGATE,0",
    ])
    data = c.get("/run/r1/phases.json").get_json()
    phases = data["phases"]
    assert len(phases) == 3
    assert phases[0]["state"] == "IDLE"
    assert phases[1]["state"] == "TAKEOFF"


def test_failsafe_returns_edges(client):
    c, td = client
    _make_run(td / "r1", [
        "1000000000,39,32,0,0,0,0,0,0,0,0,24,90,12,0.7,GUIDED,1,0,IDLE,0",
        "1010000000,39,32,5,0,0,1,0,0,0,0,22,40,12,0.7,GUIDED,1,5,NAVIGATE,1",
        "1020000000,39,32,5,0,0,0,0,0,0,0,22,38,12,0.7,RTL,1,5,RETURN_HOME,1",
    ])
    data = c.get("/run/r1/failsafe.json").get_json()
    assert len(data["events"]) == 1
    assert data["events"][0]["state"] == "NAVIGATE"


def test_endpoints_404_when_missing(client):
    c, _ = client
    for path in ("track.json", "phases.json", "failsafe.json"):
        r = c.get(f"/run/missing/{path}")
        assert r.status_code == 404
