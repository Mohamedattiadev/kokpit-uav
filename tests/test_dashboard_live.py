"""N8 — dashboard_live route + overlay testleri."""
from __future__ import annotations
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "onboard"))

flask = pytest.importorskip("flask")
cv2 = pytest.importorskip("cv2")

import dashboard_live as dl  # noqa: E402


@pytest.fixture
def client():
    dl.app.testing = True
    os.environ.pop("KOKPIT_DASH_PW", None)
    return dl.app.test_client()


def test_status_route_empty(client):
    r = client.get("/status.json")
    assert r.status_code == 200
    assert r.is_json


def test_status_updates(client):
    dl.update_status({"altitude": 10.5, "battery": 24.0})
    r = client.get("/status.json")
    data = r.get_json()
    assert data["altitude"] == 10.5
    assert "ts" in data


def test_aruco_overlay_creates_jpeg():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    corners = np.array([[[10, 10], [50, 10], [50, 50], [10, 50]]], dtype=np.float32)
    jpg = dl.render_aruco_overlay(frame, [corners], confidence=0.85)
    assert len(jpg) > 0
    assert jpg[:3] == b"\xff\xd8\xff"  # JPEG magic


def test_index_html_route(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"stream.mjpg" in r.data


def test_basic_auth_when_pw_set(client):
    os.environ["KOKPIT_DASH_PW"] = "secret"
    r = client.get("/status.json")
    assert r.status_code == 401
    r2 = client.get("/status.json",
                    headers={"Authorization": "Basic dXNlcjpzZWNyZXQ="})  # user:secret
    assert r2.status_code == 200
    del os.environ["KOKPIT_DASH_PW"]
