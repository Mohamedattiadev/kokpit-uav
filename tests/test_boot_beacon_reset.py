"""M10 — BOOT_BEACON sonrası replay window reset."""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from lora_receiver import SimLoRaReceiver  # noqa: E402
from packet_protocol import (DeliveryRequest, encode_boot_beacon,  # noqa: E402
                             encode_delivery_request)


def test_boot_beacon_clears_seen_seqs():
    rx = SimLoRaReceiver()
    req = DeliveryRequest(lat=39.0, lon=33.0, alt=20.0,
                          recipient_id=0, gps_fix=3, num_sats=10)
    rx.inject_delivery(req, seq=100)
    assert 100 in rx.parser._seen_set
    rx.inject_raw(encode_boot_beacon(seq_start=0))
    assert len(rx.parser._seen_set) == 0
    assert rx.peer_seq_start == 0


def test_old_seq_accepted_after_boot_beacon():
    rx = SimLoRaReceiver()
    req = DeliveryRequest(lat=39.0, lon=33.0, alt=20.0,
                          recipient_id=0, gps_fix=3, num_sats=10)
    rx.inject_delivery(req, seq=50)
    rx.inject_delivery(req, seq=50)   # 2. kez = replay drop
    drops_before = rx.parser.replay_drops
    assert drops_before >= 1
    rx.inject_raw(encode_boot_beacon(seq_start=0))
    rx.inject_delivery(req, seq=50)   # reboot sonrası tekrar kabul
    drops_after = rx.parser.replay_drops
    assert drops_after == drops_before  # ek drop yok


def test_boot_beacon_payload_decoded():
    rx = SimLoRaReceiver()
    rx.inject_raw(encode_boot_beacon(seq_start=12345, fw_version=2))
    assert rx.peer_seq_start == 12345


def test_expected_seq_resets_on_boot():
    rx = SimLoRaReceiver()
    req = DeliveryRequest(lat=39.0, lon=33.0, alt=20.0,
                          recipient_id=0, gps_fix=3, num_sats=10)
    rx.inject_delivery(req, seq=200)
    assert rx._expected_seq == 201
    rx.inject_raw(encode_boot_beacon(seq_start=0))
    assert rx._expected_seq is None
