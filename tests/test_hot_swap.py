"""N9 — ESP32 hot swap (station_id) testleri."""
from __future__ import annotations
import struct

from packet_protocol import encode_boot_beacon, StreamParser, MsgType
from lora_receiver import BaseLoRaReceiver


def test_boot_beacon_payload_with_station_id():
    frame = encode_boot_beacon(seq_start=100, fw_version=1, station_id=0xCAFEBABE)
    p = StreamParser()
    pkts = p.feed(frame)
    assert len(pkts) == 1
    pkt = pkts[0]
    assert pkt.msg_type == MsgType.BOOT_BEACON
    assert len(pkt.payload) == 12
    seq_start, fw, station = struct.unpack("<III", pkt.payload[:12])
    assert seq_start == 100
    assert fw == 1
    assert station == 0xCAFEBABE


def test_receiver_decodes_station_id():
    rx = BaseLoRaReceiver()
    rx._ingest(encode_boot_beacon(50, 1, 0xAA00AA00))
    assert rx.peer_station_id == 0xAA00AA00
    assert rx.peer_seq_start == 50


def test_hot_swap_detection(capsys):
    rx = BaseLoRaReceiver()
    rx._ingest(encode_boot_beacon(10, 1, 0x11111111))
    capsys.readouterr()
    rx._ingest(encode_boot_beacon(11, 1, 0x22222222))
    out = capsys.readouterr().out
    assert "hot-swap" in out


def test_legacy_8byte_payload_backcompat():
    # Eski ESP32 payload 8 byte — parser çakılmamalı
    import struct
    from packet_protocol import _frame
    payload = struct.pack("<II", 5, 1)
    legacy_frame = _frame(MsgType.BOOT_BEACON, 5, 0, 1, payload)
    rx = BaseLoRaReceiver()
    rx._ingest(legacy_frame)
    assert rx.peer_seq_start == 5
    assert rx.peer_station_id is None  # legacy: yok
