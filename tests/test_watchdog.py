"""M4 — watchdog smoke + sdnotify mock testleri."""
from __future__ import annotations
import os
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

import watchdog as wd  # noqa: E402


def test_watchdog_no_sdnotify_noop(monkeypatch):
    monkeypatch.setattr(wd, "_HAS", False)
    w = wd.Watchdog(period_s=0.0)
    w.ready()
    assert w.notify() is False   # notifier yok


def test_watchdog_period_skip():
    w = wd.Watchdog(period_s=1.0)
    w._notifier = MagicMock()
    assert w.notify() is True
    assert w.notify() is False    # period geçmedi
    time.sleep(1.05)
    assert w.notify() is True


def test_ready_idempotent():
    w = wd.Watchdog()
    mock = MagicMock()
    w._notifier = mock
    w.ready()
    w.ready()
    assert mock.notify.call_count == 1


def test_stopping_sends_status():
    w = wd.Watchdog()
    mock = MagicMock()
    w._notifier = mock
    w.stopping("test reason")
    mock.notify.assert_called_once()
    arg = mock.notify.call_args[0][0]
    assert "STOPPING=1" in arg and "test reason" in arg


def test_systemd_unit_file_present():
    path = os.path.join(os.path.dirname(__file__), "..",
                        "systemd", "kokpit-mc.service")
    assert os.path.exists(path)
    with open(path) as f:
        txt = f.read()
    assert "Type=notify" in txt
    assert "WatchdogSec=" in txt
    assert "Restart=on-failure" in txt
