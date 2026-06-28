"""M7 — LoRa link stats + telemetry packet testleri."""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from lora_receiver import SimLoRaReceiver  # noqa: E402
from packet_protocol import (DeliveryRequest, decode_telemetry,  # noqa: E402
                             encode_telemetry, MsgType, StreamParser)
from telemetry_tx import TelemetryTx  # noqa: E402


def test_link_stats_after_no_packets():
    rx = SimLoRaReceiver()
    s = rx.link_stats()
    assert s["received"] == 0
    assert s["packet_loss_pct"] == 0.0
    assert s["rx_rate_hz"] == 0.0


def test_link_stats_after_inject():
    rx = SimLoRaReceiver()
    req = DeliveryRequest(lat=39.0, lon=33.0, alt=20.0,
                          recipient_id=0, gps_fix=3, num_sats=10)
    rx.inject_delivery(req, seq=1)
    s = rx.link_stats()
    assert s["received"] >= 1
    assert s["rx_rate_hz"] >= 1.0


def test_packet_loss_detected_from_seq_gap():
    rx = SimLoRaReceiver()
    req = DeliveryRequest(lat=39.0, lon=33.0, alt=20.0,
                          recipient_id=0, gps_fix=3, num_sats=10)
    rx.inject_delivery(req, seq=10)
    rx.inject_delivery(req, seq=15)   # 4 missed
    s = rx.link_stats()
    assert s["missed"] >= 4
    assert s["packet_loss_pct"] > 0


def test_telemetry_encode_decode_roundtrip():
    pkt = encode_telemetry(mode_id=4, batt_mv=22500, phase=3,
                           rssi_dbm=-80, loss_pct=12, seq=99)
    parser = StreamParser()
    out = list(parser.feed(pkt))
    assert len(out) == 1
    p = out[0]
    assert p.msg_type == MsgType.TELEMETRY
    mode, batt, phase, rssi, loss = decode_telemetry(p.payload)
    assert mode == 4 and batt == 22500 and phase == 3
    assert rssi == -80 and loss == 12


def test_telemetry_tx_builds_without_send():
    drone = MagicMock()
    drone.telemetry.return_value = MagicMock(
        mode="GUIDED", battery_voltage=22.4)
    lora = MagicMock()
    lora.last_rssi = -75
    lora.packet_loss_pct.return_value = 5.0
    tx = TelemetryTx(drone, lora=lora, send_raw=None)
    pkt = tx.tick()
    assert isinstance(pkt, bytes) and len(pkt) > 0
