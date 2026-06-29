"""#12 — /health endpoint testleri."""
from __future__ import annotations
import pytest

flask = pytest.importorskip("flask")
import dashboard_live as dl


@pytest.fixture
def client():
    dl.app.testing = True
    dl._health_providers.clear()
    yield dl.app.test_client()
    dl._health_providers.clear()


def test_health_no_providers_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True


def test_health_all_ok(client):
    dl.register_health("mavlink", lambda: (True, "heartbeat 0.5s"))
    dl.register_health("lora", lambda: (True, "rx 8 Hz"))
    r = client.get("/health")
    data = r.get_json()
    assert data["ok"] is True
    assert data["components"]["mavlink"]["ok"]
    assert data["components"]["lora"]["detail"] == "rx 8 Hz"


def test_health_one_failure_overall_fail(client):
    dl.register_health("mavlink", lambda: (True, "OK"))
    dl.register_health("recorder", lambda: (False, "stopped"))
    r = client.get("/health")
    data = r.get_json()
    assert data["ok"] is False
    assert data["components"]["recorder"]["ok"] is False


def test_health_provider_exception_counts_as_fail(client):
    def bad():
        raise RuntimeError("simulated")
    dl.register_health("camera", bad)
    r = client.get("/health")
    data = r.get_json()
    assert data["ok"] is False
    assert "exc" in data["components"]["camera"]["detail"]
