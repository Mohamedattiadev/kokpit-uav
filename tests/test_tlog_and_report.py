"""#14+#15 — tlog export + PDF report testleri."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "scripts"))

flask = pytest.importorskip("flask")
import replay_dashboard as rd


CSV_HEADER = ("ts_unix_us,lat,lon,alt_rel,vx,vy,vz,heading,roll,pitch,yaw,"
              "battery_v,battery_pct,satellites,hdop,mode,armed,lidar_alt_body,"
              "mission_state,failsafe_active")


def _mkrun(d: Path):
    d.mkdir(parents=True, exist_ok=True)
    (d / "events.jsonl").write_text(
        json.dumps({"ts": 1000, "event": "start"}) + "\n" +
        json.dumps({"ts": 1120, "event": "package_delivered",
                    "recipient_id": 7}) + "\n"
    )
    (d / "telemetry.csv").write_text(CSV_HEADER + "\n" + "\n".join([
        "1000000000,39.92,32.85,0,0,0,0,0,0,0,0,24.5,90,12,0.7,GUIDED,1,0,IDLE,0",
        "1060000000,39.921,32.851,10,1,0,0,90,0,0.01,1.57,24.2,86,12,0.7,GUIDED,1,10,NAVIGATE,0",
        "1120000000,39.921,32.851,2.5,0,0,0,90,0,0,1.57,24.0,82,12,0.7,GUIDED,1,2.5,DROP_PACKAGE,0",
    ]))


def test_make_report_md_tr(tmp_path):
    from make_report import build_report_md
    _mkrun(tmp_path / "r1")
    md = build_report_md(tmp_path / "r1", lang="tr")
    assert "Görev Raporu" in md
    assert "Başarılı teslimat" in md
    assert "Önemli rakamlar" in md


def test_make_report_md_en(tmp_path):
    from make_report import build_report_md
    _mkrun(tmp_path / "r1")
    md = build_report_md(tmp_path / "r1", lang="en")
    assert "Mission Report" in md
    assert "Delivered" in md
    assert "Key numbers" in md


def test_csv_to_tlog(tmp_path):
    from csv_to_tlog import csv_to_tlog
    _mkrun(tmp_path / "r1")
    out = tmp_path / "track.tlog"
    n = csv_to_tlog(tmp_path / "r1" / "telemetry.csv", out)
    assert n == 3
    assert out.exists()
    # tlog format: 8 byte uint64 timestamp + mavlink frame (starts with 0xFD v2 or 0xFE v1)
    data = out.read_bytes()
    assert len(data) > 8
    # First frame after timestamp prefix should be mavlink magic
    assert data[8] in (0xFD, 0xFE)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "RUNS_DIR", tmp_path)
    rd.app.testing = True
    return rd.app.test_client(), tmp_path


def test_report_md_endpoint(client):
    c, td = client
    _mkrun(td / "r1")
    r = c.get("/run/r1/report.md?lang=en")
    assert r.status_code == 200
    assert r.mimetype == "text/markdown"
    assert b"Mission Report" in r.data
    r2 = c.get("/run/r1/report.md?lang=tr")
    assert "Görev Raporu".encode() in r2.data


def test_report_html_endpoint(client):
    c, td = client
    _mkrun(td / "r1")
    r = c.get("/run/r1/report.html?lang=tr")
    assert r.status_code == 200
    assert b"<table" in r.data
    assert "Görev Raporu".encode() in r.data
    assert b"KOKPIT" in r.data


def test_tlog_endpoint(client):
    c, td = client
    _mkrun(td / "r1")
    r = c.get("/run/r1/track.tlog")
    assert r.status_code == 200


def test_tlog_404_no_telemetry(client):
    c, td = client
    (td / "r1").mkdir()
    r = c.get("/run/r1/track.tlog")
    assert r.status_code == 404
