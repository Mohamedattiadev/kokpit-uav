"""#13 — webhook_alerter testleri (provider-neutral)."""
from __future__ import annotations
import os
import time

import webhook_alerter as wh


def test_no_url_silent(monkeypatch):
    monkeypatch.delenv("KOKPIT_WEBHOOK_URL", raising=False)
    # should not raise
    wh.notify("package_delivered", recipient_id=1)


def test_unwatched_event_not_posted(monkeypatch):
    posted = []
    monkeypatch.setenv("KOKPIT_WEBHOOK_URL", "http://example.invalid/hook")
    monkeypatch.setattr(wh, "_post", lambda u, p: posted.append((u, p)) or True)
    wh.notify("phase", state="TAKEOFF")
    time.sleep(0.1)
    assert posted == []


def test_watched_event_posts(monkeypatch):
    posted = []
    monkeypatch.setenv("KOKPIT_WEBHOOK_URL", "http://example.invalid/hook")
    monkeypatch.setattr(wh, "_post", lambda u, p: posted.append((u, p)) or True)
    wh.notify("package_delivered", recipient_id=42)
    time.sleep(0.2)
    assert len(posted) == 1
    assert posted[0][1]["event"] == "package_delivered"
    assert posted[0][1]["recipient_id"] == 42
    assert posted[0][1]["source"] == "kokpit-mc"


def test_attach_wraps_emit(tmp_path, monkeypatch):
    from event_logger import EventLogger
    posted = []
    monkeypatch.setenv("KOKPIT_WEBHOOK_URL", "http://example.invalid/hook")
    monkeypatch.setattr(wh, "_post", lambda u, p: posted.append((u, p)) or True)
    lg = EventLogger(tmp_path / "events.jsonl")
    wh.attach_to_event_logger(lg)
    lg.emit("abort", reason="LINK_LOST")
    lg.emit("phase", state="TAKEOFF")  # unwatched
    lg.close()
    time.sleep(0.2)
    assert len(posted) == 1
    assert posted[0][1]["reason"] == "LINK_LOST"
