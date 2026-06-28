"""M3 — time_sync testleri."""
from __future__ import annotations
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

import time_sync as ts  # noqa: E402


class FakeSysTimeMsg:
    def __init__(self, unix_usec):
        self.time_unix_usec = unix_usec

    def get_type(self):
        return "SYSTEM_TIME"


def test_no_sync_falls_back_to_walltime(monkeypatch):
    ts.reset()
    assert not ts.is_synced()
    now = ts.get_synced_unix_us()
    wall = int(time.time() * 1e6)
    assert abs(now - wall) < 5_000_000   # 5 sn


def test_update_sets_offset():
    ts.reset()
    fake_unix = 1_700_000_000_000_000   # 2023-11-14
    ts.update_from_system_time(fake_unix, mono_us=10_000_000)
    assert ts.is_synced()
    # offset = unix - mono
    assert ts.offset_us() == fake_unix - 10_000_000


def test_dispatch_via_listener():
    ts.reset()
    li = ts.SystemTimeListener()
    li.handle(FakeSysTimeMsg(2_000_000_000_000_000))
    assert ts.is_synced()


def test_listener_ignores_nontime_msgs():
    ts.reset()
    li = ts.SystemTimeListener()

    class Other:
        def get_type(self):
            return "HEARTBEAT"

    li.handle(Other())
    li.handle(None)
    assert not ts.is_synced()


def test_log_with_ts_includes_ts_field():
    ts.reset()
    s = ts.log_with_ts("TEST", "hello")
    assert "ts=" in s and "TEST" in s and "hello" in s
