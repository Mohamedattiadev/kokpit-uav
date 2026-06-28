"""
log_downloader.py — Pixhawk dataflash log'unu Jetson'a çek.

Görev sonrası post-mortem analiz için en yeni .BIN log'u MAVLink LOG_REQUEST_LIST
+ LOG_REQUEST_DATA ile alır. runs/YYYYMMDD_HHMMSS/dataflash.bin yazar.

Çağrı: mission disarm sonrası download_latest_log(mav, "runs").
"""
from __future__ import annotations
import os
import time
from datetime import datetime
from typing import Optional

try:
    from pymavlink import mavutil  # noqa
    _HAS_MAVUTIL = True
except Exception:
    _HAS_MAVUTIL = False


CHUNK_SIZE = 90


def _request_list(mav) -> Optional[tuple[int, int]]:
    """LOG_REQUEST_LIST → (last_id, size_bytes) son log için."""
    mav.master.mav.log_request_list_send(
        mav.master.target_system, mav.master.target_component, 0, 0xFFFF)
    entry = mav.master.recv_match(type="LOG_ENTRY", blocking=True, timeout=5.0)
    if entry is None:
        return None
    # ArduPilot last_log_num via entry.last_log_num
    return entry.last_log_num, entry.size


def download_latest_log(mav, output_dir: str = "runs",
                        timeout_s: float = 120.0) -> Optional[str]:
    """En yeni dataflash log'u indir. Çıktı yolu döner veya None."""
    if mav is None or getattr(mav, "master", None) is None:
        return None
    info = _request_list(mav)
    if info is None:
        print("[LOG] LOG_ENTRY alınamadı")
        return None
    last_id, size = info
    if size <= 0:
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(output_dir, ts)
    os.makedirs(run_dir, exist_ok=True)
    out = os.path.join(run_dir, "dataflash.bin")
    received = bytearray(size)
    offset = 0
    deadline = time.time() + timeout_s
    while offset < size and time.time() < deadline:
        n = min(CHUNK_SIZE, size - offset)
        mav.master.mav.log_request_data_send(
            mav.master.target_system, mav.master.target_component,
            last_id, offset, n)
        msg = mav.master.recv_match(type="LOG_DATA", blocking=True, timeout=2.0)
        if msg is None:
            continue
        chunk = bytes(msg.data[:msg.count])
        end = min(offset + len(chunk), size)
        received[offset:end] = chunk[: end - offset]
        offset += msg.count
    with open(out, "wb") as f:
        f.write(received)
    print(f"[LOG] indirildi: {out} ({offset}/{size} byte)")
    return out
