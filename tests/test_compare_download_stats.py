"""#6+#7+#8 — compare + download + stats endpoint testleri."""
from __future__ import annotations
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

flask = pytest.importorskip("flask")
import replay_dashboard as rd


def _mkrun(d: Path, delivered=False, abort_reason=""):
    d.mkdir(parents=True, exist_ok=True)
    events = [{"ts": 1000, "event": "start"}]
    if delivered:
        events.append({"ts": 1100, "event": "package_delivered"})
    if abort_reason:
        events.append({"ts": 1080, "event": "abort", "reason": abort_reason})
    (d / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    (d / "telemetry.csv").write_text("h\n" + "x\n" * 5)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "RUNS_DIR", tmp_path)
    rd.app.testing = True
    return rd.app.test_client(), tmp_path


def test_stats_aggregates(client):
    c, td = client
    _mkrun(td / "r1", delivered=True)
    _mkrun(td / "r2", delivered=True)
    _mkrun(td / "r3", abort_reason="BATTERY_LOW")
    r = c.get("/api/stats")
    data = r.get_json()
    assert data["total_runs"] == 3
    assert data["delivered"] == 2
    assert data["aborted"] == 1
    assert data["success_rate_pct"] == 66.7


def test_stats_empty(client):
    c, _ = client
    data = c.get("/api/stats").get_json()
    assert data["total_runs"] == 0
    assert data["success_rate_pct"] == 0.0


def test_download_returns_zip(client):
    c, td = client
    _mkrun(td / "r1", delivered=True)
    r = c.get("/run/r1/download.zip")
    assert r.status_code == 200
    assert r.mimetype == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.data))
    names = z.namelist()
    assert "r1/events.jsonl" in names
    assert "r1/telemetry.csv" in names


def test_download_404(client):
    c, _ = client
    r = c.get("/run/missing/download.zip")
    assert r.status_code == 404


def test_compare_page_renders(client):
    c, td = client
    _mkrun(td / "r1", delivered=True)
    _mkrun(td / "r2", abort_reason="LINK_LOST")
    r = c.get("/compare?a=r1&b=r2")
    assert r.status_code == 200
    assert b"r1" in r.data and b"r2" in r.data
    assert b"LINK_LOST" in r.data


def test_compare_404_missing(client):
    c, td = client
    _mkrun(td / "r1")
    r = c.get("/compare?a=r1&b=missing")
    assert r.status_code == 404


def test_compare_400_bad_name(client):
    c, _ = client
    r = c.get("/compare?a=../etc&b=passwd")
    assert r.status_code == 400
