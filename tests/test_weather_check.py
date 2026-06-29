"""N6 — weather_check testleri."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from weather_check import evaluate, check  # noqa: E402


def test_calm_go():
    d = evaluate(wind_ms=2.0, precip_mmh=0.0, visibility_m=20000.0)
    assert d.go


def test_windy_nogo():
    d = evaluate(wind_ms=8.0, precip_mmh=0.0, visibility_m=10000.0)
    assert not d.go
    assert "rüzgar" in d.reason


def test_rain_nogo():
    d = evaluate(wind_ms=2.0, precip_mmh=0.5, visibility_m=10000.0)
    assert not d.go
    assert "yağmur" in d.reason


def test_low_visibility_nogo():
    d = evaluate(wind_ms=2.0, precip_mmh=0.0, visibility_m=500.0)
    assert not d.go
    assert "görüş" in d.reason


def test_offline_mock_skip():
    def offline_fetch(lat, lon):
        raise ConnectionError("no internet")
    d = check(39.9, 32.8, fetch_fn=offline_fetch)
    assert d.go  # skip = go (uyarı verilir ama bloklamaz)
    assert "skip" in d.reason


def test_api_response_mock():
    def mock_fetch(lat, lon):
        return {"current": {
            "wind_speed_10m": 3.0,
            "precipitation": 0.0,
            "visibility": 15000.0,
        }}
    d = check(39.9, 32.8, fetch_fn=mock_fetch)
    assert d.go
    assert d.wind_ms == 3.0
