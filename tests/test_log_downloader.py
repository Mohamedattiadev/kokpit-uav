"""M5 — log_downloader + plot_mission testleri."""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import log_downloader as ld  # noqa: E402
import plot_mission as pm  # noqa: E402


class FakeEntry:
    def __init__(self, last_log_num, size):
        self.last_log_num = last_log_num
        self.size = size

    def get_type(self):
        return "LOG_ENTRY"


class FakeChunk:
    def __init__(self, data, count):
        self.data = data
        self.count = count

    def get_type(self):
        return "LOG_DATA"


def _make_mav(size=200):
    """Mock mavutil-like object: recv_match dispatch LOG_ENTRY + LOG_DATA."""
    mav = MagicMock()
    master = MagicMock()
    mav.master = master
    master.target_system = 1
    master.target_component = 1

    payload = b"X" * size
    state = {"idx": 0}

    def recv(type, blocking, timeout):
        if state["idx"] == 0:
            state["idx"] = 1
            return FakeEntry(42, size)
        # Aşağıdaki çağrılar log_request_data sonrası chunk dönüyor
        # Basitleştirme: 90'lık parça döndür offset bilgisi yok
        n = min(90, size)
        return FakeChunk(payload[:n] + b"\x00" * (90 - n), n)

    master.recv_match.side_effect = recv
    return mav


def test_download_none_when_no_mav():
    assert ld.download_latest_log(None) is None


def test_download_writes_file(tmp_path):
    mav = _make_mav(size=120)
    out = ld.download_latest_log(mav, output_dir=str(tmp_path), timeout_s=5.0)
    assert out is not None and os.path.exists(out)
    sz = os.path.getsize(out)
    assert sz == 120


def test_download_no_entry():
    mav = MagicMock()
    mav.master = MagicMock()
    mav.master.recv_match.return_value = None
    assert ld.download_latest_log(mav) is None


def test_plot_summarize_empty():
    s = pm.summarize([])
    assert s["count"] == 0


def test_plot_parse_jsonl(tmp_path):
    f = tmp_path / "e.jsonl"
    f.write_text('{"ts":1,"phase":"TAKEOFF"}\n{"ts":2,"phase":"NAVIGATE"}\n')
    ev = pm.parse_jsonl_events(str(f))
    assert len(ev) == 2
    assert pm.summarize(ev)["count"] == 2
