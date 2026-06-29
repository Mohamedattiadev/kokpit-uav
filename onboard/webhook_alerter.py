"""#13 — Generic webhook alerter (Slack/Discord/Telegram bot uyumlu).

KOKPIT_WEBHOOK_URL set ise package_delivered + abort eventinde JSON POST.
Provider-bağımsız: kullanıcı bot proxy kurar.
"""
from __future__ import annotations
import json
import os
import threading
from typing import Optional


WATCH_EVENTS = ("package_delivered", "abort", "mission_end")


def _post(url: str, payload: dict, timeout: float = 5.0) -> bool:
    try:
        import requests
        r = requests.post(url, json=payload, timeout=timeout)
        return r.status_code < 400
    except Exception as e:
        print(f"[ALERT] post hatası: {e}")
        return False


def notify(event: str, **payload) -> None:
    """Event watch listesindeyse webhook POST (async, mission'ı bloklamaz)."""
    if event not in WATCH_EVENTS:
        return
    url = os.environ.get("KOKPIT_WEBHOOK_URL")
    if not url:
        return
    body = {"event": event, "source": "kokpit-mc", **payload}
    threading.Thread(target=_post, args=(url, body), daemon=True).start()


def attach_to_event_logger(logger) -> None:
    """EventLogger.emit'i wrap et — orijinal davranış + webhook notify."""
    orig = logger.emit

    def wrapped(event: str, **payload):
        orig(event, **payload)
        notify(event, **payload)
    logger.emit = wrapped
