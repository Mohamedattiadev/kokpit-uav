"""İŞ-3 — ESP32 RX parser (packet_protocol.h / KokpitStreamParser) doğrulaması.

Gerçek ESP32 donanımı yokken yapılabilecek en yakın doğrulama: firmware'deki
`packet_protocol.h` içindeki C++ parser'ı host (g++) üzerinde, gerçek SHA-256
implementasyonuyla derleyip Python tarafının (`onboard/packet_protocol.py`)
ürettiği ikili paketleri besleyerek round-trip + hata senaryolarını test eder.
KOKPIT_AES_ENABLED derlemede tanımlı DEĞİL (plaintext mod) — bu da
onboard/packet_protocol.py'nin AES anahtar dosyası yokken düştüğü varsayılan
geliştirme moduyla birebir eşleşir.

g++ yoksa (CI ortamı) testler skip edilir.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))
from packet_protocol import (  # noqa: E402
    encode_abort,
    encode_manual_request,
    encode_telemetry,
    MsgType,
)

HARNESS_DIR = os.path.join(os.path.dirname(__file__), "esp32_harness")
HARNESS_SRC = os.path.join(HARNESS_DIR, "harness_main.cpp")
HARNESS_BIN = os.path.join(HARNESS_DIR, "harness")

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="g++ yok, ESP32 parser host derlemesi atlanıyor")


@pytest.fixture(scope="module")
def harness():
    subprocess.run(
        ["g++", "-std=c++17", "-I", HARNESS_DIR, "-o", HARNESS_BIN, HARNESS_SRC],
        check=True, capture_output=True, text=True)
    return HARNESS_BIN


def run_harness(harness, raw: bytes) -> str:
    r = subprocess.run([harness, raw.hex()], check=True,
                       capture_output=True, text=True)
    return r.stdout


def parse_pkt_lines(output: str):
    pkts = []
    for line in output.splitlines():
        if not line.startswith("PKT "):
            continue
        fields = dict(tok.split("=", 1) for tok in line[len("PKT "):].split())
        pkts.append(fields)
    return pkts


def parse_stats(output: str) -> dict:
    for line in output.splitlines():
        if line.startswith("STATS "):
            return dict(tok.split("=", 1) for tok in line[len("STATS "):].split())
    raise AssertionError(f"STATS satırı yok: {output}")


def test_telemetry_roundtrip(harness):
    raw = encode_telemetry(mode_id=3, batt_mv=22400, phase=5,
                           rssi_dbm=-78, loss_pct=5, seq=42)
    out = run_harness(harness, raw)
    pkts = parse_pkt_lines(out)
    assert len(pkts) == 1
    p = pkts[0]
    assert int(p["msg"]) == int(MsgType.TELEMETRY)
    assert int(p["seq"]) == 42
    # TELEMETRY_FMT = "<BHBbB": mode_id, batt_mv(u16 LE), phase, rssi(i8), loss
    payload = bytes.fromhex(p["payload"])
    assert payload[0] == 3
    assert int.from_bytes(payload[1:3], "little") == 22400
    assert payload[3] == 5
    rssi_signed = payload[4] - 256 if payload[4] > 127 else payload[4]
    assert rssi_signed == -78
    assert payload[5] == 5
    stats = parse_stats(out)
    assert stats["crc"] == "0" and stats["sha"] == "0" and stats["replay"] == "0"


def test_manual_request_roundtrip(harness):
    raw = encode_manual_request("LOITER", seq=7)
    out = run_harness(harness, raw)
    pkts = parse_pkt_lines(out)
    assert len(pkts) == 1
    assert int(pkts[0]["msg"]) == int(MsgType.MANUAL_REQUEST)
    payload = bytes.fromhex(pkts[0]["payload"])
    assert payload.rstrip(b"\x00").decode("ascii") == "LOITER"


def test_abort_roundtrip(harness):
    raw = encode_abort(seq=99)
    out = run_harness(harness, raw)
    pkts = parse_pkt_lines(out)
    assert len(pkts) == 1
    assert int(pkts[0]["msg"]) == int(MsgType.ABORT)
    assert pkts[0]["payload"] == ""


def test_multiple_packets_back_to_back(harness):
    raw = (encode_telemetry(1, 20000, 1, -50, 0, seq=1) +
          encode_telemetry(2, 20100, 2, -55, 1, seq=2) +
          encode_abort(seq=3))
    out = run_harness(harness, raw)
    pkts = parse_pkt_lines(out)
    assert [int(p["seq"]) for p in pkts] == [1, 2, 3]


def test_bit_flip_crc_error_then_resync(harness):
    good = encode_telemetry(1, 20000, 1, -50, 0, seq=10)
    corrupted = bytearray(good)
    corrupted[15] ^= 0xFF   # payload içinde bir bit çevir -> CRC uyuşmaz
    raw = bytes(corrupted) + encode_telemetry(2, 21000, 2, -60, 2, seq=11)
    out = run_harness(harness, raw)
    pkts = parse_pkt_lines(out)
    # Bozuk paket düşürülmeli, ikinci geçerli paket yakalanmalı
    assert [int(p["seq"]) for p in pkts] == [11]
    stats = parse_stats(out)
    assert int(stats["crc"]) >= 1


def test_replay_duplicate_seq_dropped(harness):
    pkt = encode_telemetry(1, 20000, 1, -50, 0, seq=55)
    raw = pkt + pkt   # aynı paketi iki kez gönder
    out = run_harness(harness, raw)
    pkts = parse_pkt_lines(out)
    assert len(pkts) == 1   # ikincisi replay olarak düşmeli
    stats = parse_stats(out)
    assert int(stats["replay"]) == 1


def test_garbage_prefix_resyncs_to_valid_packet(harness):
    garbage = bytes([0x00, 0xFF, 0x4B, 0x41, 0x99])  # yanlış magic + gürültü
    raw = garbage + encode_telemetry(1, 20000, 1, -50, 0, seq=77)
    out = run_harness(harness, raw)
    pkts = parse_pkt_lines(out)
    assert len(pkts) == 1
    assert int(pkts[0]["seq"]) == 77
