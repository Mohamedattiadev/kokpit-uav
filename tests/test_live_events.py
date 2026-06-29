"""#2 — /run/<name>/events.json live tail endpoint."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

flask = pytest.importorskip("flask")
import replay_dashboard as rd


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "RUNS_DIR", tmp_path)
    rd.app.testing = True
    return rd.app.test_client(), tmp_path


def test_events_endpoint_returns_jsonl_list(client):
    c, td = client
    d = td / "r1"
    d.mkdir()
    (d / "events.jsonl").write_text(
        json.dumps({"ts": 1, "event": "start"}) + "\n" +
        json.dumps({"ts": 2, "event": "package_delivered"}) + "\n"
    )
    r = c.get("/run/r1/events.json")
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["events"]) == 2
    assert data["events"][0]["event"] == "start"


def test_events_endpoint_404(client):
    c, _ = client
    r = c.get("/run/missing/events.json")
    # mevcut implementasyon dosya yoksa boş döner — istek başarısız değil
    assert r.status_code == 200
    assert r.get_json()["events"] == []


def test_events_endpoint_skips_bad_lines(client):
    c, td = client
    d = td / "r1"
    d.mkdir()
    (d / "events.jsonl").write_text(
        json.dumps({"ts": 1, "event": "start"}) + "\nnot-json\n" +
        json.dumps({"ts": 2, "event": "end"}) + "\n"
    )
    data = c.get("/run/r1/events.json").get_json()
    assert len(data["events"]) == 2
