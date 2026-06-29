"""N3 — replay_dashboard route smoke testleri."""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

flask = pytest.importorskip("flask")

import replay_dashboard as rd  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "RUNS_DIR", tmp_path)
    rd.app.testing = True
    return rd.app.test_client()


def test_index_route_200(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Kokpit" in r.data or b"Replay" in r.data


def test_index_lists_runs(client, tmp_path):
    (tmp_path / "20260101_120000").mkdir()
    r = client.get("/")
    assert r.status_code == 200
    assert b"20260101_120000" in r.data


def test_run_view_404_when_missing(client):
    r = client.get("/run/nonexistent")
    assert r.status_code == 404


def test_run_view_path_traversal_blocked(client):
    r = client.get("/run/..%2Fetc")
    assert r.status_code in (400, 404)


def test_api_runs_json(client, tmp_path):
    (tmp_path / "run_a").mkdir()
    (tmp_path / "run_b").mkdir()
    r = client.get("/api/runs")
    assert r.status_code == 200
    data = r.get_json()
    assert set(data["runs"]) == {"run_a", "run_b"}
