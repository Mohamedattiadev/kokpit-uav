"""LoRa paket protokolü testleri — CRC, roundtrip, akış ayrıştırma, hatalı paket."""
import struct
import pytest

from packet_protocol import (
    DeliveryRequest, encode_delivery_request, decode_delivery_request,
    StreamParser, crc16_ccitt, MsgType, encode_abort, MAGIC0, MAGIC1,
)


def test_crc_known_vector():
    # CRC-16/CCITT-FALSE, "123456789" -> 0x29B1 (standart test vektörü)
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_delivery_roundtrip():
    req = DeliveryRequest(lat=39.925533, lon=32.866287, alt=901.5,
                          recipient_id=7, gps_fix=3, num_sats=12,
                          timestamp_ms=123456)
    raw = encode_delivery_request(req, seq=5)
    p = StreamParser()
    pkts = p.feed(raw)
    assert len(pkts) == 1
    assert pkts[0].msg_type == MsgType.DELIVERY_REQUEST
    got = decode_delivery_request(pkts[0].payload)
    assert abs(got.lat - req.lat) < 1e-6
    assert abs(got.lon - req.lon) < 1e-6
    assert abs(got.alt - req.alt) < 1e-3
    assert got.recipient_id == 7
    assert got.num_sats == 12


def test_stream_with_noise_and_split():
    req = DeliveryRequest(lat=10.0, lon=20.0, alt=100.0, recipient_id=3,
                          gps_fix=3, num_sats=9)
    raw = encode_delivery_request(req)
    p = StreamParser()
    # baş tarafa çöp, paketi ikiye böl
    out = p.feed(b"\x00\xAA\xFF" + raw[:4])
    out += p.feed(raw[4:] + b"\x12\x34")
    assert len(out) == 1
    # baştaki 3 çöp bayt atılmalı (sondaki bayt sonraki magic aranırken atılabilir)
    assert p.bytes_dropped >= 3


def test_corrupted_crc_rejected():
    req = DeliveryRequest(lat=1.0, lon=2.0, alt=3.0, recipient_id=1,
                          gps_fix=3, num_sats=8)
    raw = bytearray(encode_delivery_request(req))
    raw[10] ^= 0xFF  # payload'ı boz
    p = StreamParser()
    out = p.feed(bytes(raw))
    assert out == []
    assert p.crc_errors == 1


def test_multiple_packets():
    p = StreamParser()
    a = encode_delivery_request(DeliveryRequest(1, 2, 3, 1, 3, 8))
    b = encode_abort()
    out = p.feed(a + b)
    assert len(out) == 2
    assert out[0].msg_type == MsgType.DELIVERY_REQUEST
    assert out[1].msg_type == MsgType.ABORT


def test_invalid_fix_detection():
    bad = DeliveryRequest(lat=0.0, lon=0.0, alt=0.0, recipient_id=1,
                          gps_fix=1, num_sats=2)
    assert not bad.is_valid_fix()
    good = DeliveryRequest(lat=39.9, lon=32.8, alt=900, recipient_id=1,
                           gps_fix=3, num_sats=10)
    assert good.is_valid_fix()


def test_decode_wrong_size_raises():
    with pytest.raises(ValueError):
        decode_delivery_request(b"\x00\x01\x02")
