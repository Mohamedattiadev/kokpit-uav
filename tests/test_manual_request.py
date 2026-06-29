"""Manual override — RC + LoRa MANUAL_REQUEST testleri.

Pilot her zaman kontrolü alabilmeli: (1) RC mode switch ile (M9 PILOT_OVERRIDE
failsafe), (2) yer istasyonu LoRa MANUAL_REQUEST paketiyle (RC link zayıfsa).
"""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from lora_receiver import SimLoRaReceiver  # noqa: E402
from packet_protocol import (MsgType, StreamParser,  # noqa: E402
                             encode_manual_request)
from mission import Mission  # noqa: E402


def test_manual_request_encode_decode():
    pkt = encode_manual_request("LOITER", seq=1)
    parser = StreamParser()
    out = list(parser.feed(pkt))
    assert len(out) == 1
    assert out[0].msg_type == MsgType.MANUAL_REQUEST


def test_lora_manual_request_sets_flag():
    rx = SimLoRaReceiver()
    rx.inject_raw(encode_manual_request("LOITER", seq=5))
    assert rx.manual_requested is True
    assert rx.manual_target_mode == "LOITER"


def test_lora_manual_request_custom_mode():
    rx = SimLoRaReceiver()
    rx.inject_raw(encode_manual_request("STABILIZE", seq=6))
    assert rx.manual_target_mode == "STABILIZE"


def test_mission_abort_check_triggers_set_mode():
    drone = MagicMock()
    drone.telemetry.return_value = MagicMock(armed=True, mode="GUIDED")
    drone.set_mode.return_value = True
    lora = MagicMock()
    lora.abort_requested = False
    lora.manual_requested = True
    lora.manual_target_mode = "LOITER"
    m = Mission(drone=drone, lora=lora)
    m.dropper = MagicMock()
    assert m.abort_check() is True
    drone.set_mode.assert_called_with("LOITER")
    assert "PILOT_OVERRIDE" in m._abort_reason


def test_pilot_override_abort_skips_rtl():
    """_do_abort: PILOT_OVERRIDE reason → drone.set_mode RTL ÇAĞRILMAMALI."""
    drone = MagicMock()
    drone.telemetry.return_value = MagicMock(armed=False)
    m = Mission(drone=drone, lora=MagicMock())
    m.dropper = MagicMock()
    m._abort_reason = "[PILOT_OVERRIDE] test"
    m._do_abort()
    # set_mode("RTL") veya set_mode("LAND") çağrılmamış olmalı
    rtl_calls = [c for c in drone.set_mode.call_args_list
                 if c.args and c.args[0] in ("RTL", "LAND")]
    assert len(rtl_calls) == 0
