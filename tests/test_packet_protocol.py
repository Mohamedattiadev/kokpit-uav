"""LoRa paket protokolü testleri (v2):
CRC + AES (plaintext fallback) + SHA + replay + chunk reassembly + roundtrip."""
import struct
import pytest

from packet_protocol import (
    DeliveryRequest, FaceImageBegin,
    encode_delivery_request, decode_delivery_request,
    encode_face_image_begin, encode_face_image_chunk,
    encode_abort, encode_boot_beacon,
    StreamParser, ImageReassembler,
    crc16_ccitt, MsgType, MAGIC0, MAGIC1,
)


def test_crc_known_vector():
    # CRC-16/CCITT-FALSE, "123456789" -> 0x29B1
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
    raw = encode_delivery_request(req, seq=100)
    p = StreamParser()
    out = p.feed(b"\x00\xAA\xFF" + raw[:4])
    out += p.feed(raw[4:] + b"\x12\x34")
    assert len(out) == 1
    assert p.bytes_dropped >= 3


def test_corrupted_crc_rejected():
    req = DeliveryRequest(lat=1.0, lon=2.0, alt=3.0, recipient_id=1,
                          gps_fix=3, num_sats=8)
    raw = bytearray(encode_delivery_request(req, seq=10))
    # SHA alanı header'da [10:18] — bozarsak CRC fail (header CRC'ye dahil)
    raw[10] ^= 0xFF
    p = StreamParser()
    out = p.feed(bytes(raw))
    assert out == []
    assert p.crc_errors >= 1


def test_multiple_packets():
    p = StreamParser()
    a = encode_delivery_request(DeliveryRequest(1, 2, 3, 1, 3, 8), seq=1)
    b = encode_abort(seq=2)
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


# -------- v2 yeni testler --------

def test_replay_protection():
    req = DeliveryRequest(lat=39.9, lon=32.8, alt=900, recipient_id=1,
                          gps_fix=3, num_sats=10)
    raw = encode_delivery_request(req, seq=42)
    p = StreamParser()
    out1 = p.feed(raw)
    out2 = p.feed(raw)   # aynı seq — replay
    assert len(out1) == 1
    assert len(out2) == 0
    assert p.replay_drops == 1


def test_face_image_chunk_reassembly():
    fb = FaceImageBegin(lat=39.9, lon=32.8, alt=900, gps_fix=3, num_sats=10,
                        jpeg_len=300, jpeg_total_chunks=3, img_seq=1,
                        timestamp_ms=0)
    p = StreamParser()
    r = ImageReassembler()

    # BEGIN
    begin_raw = encode_face_image_begin(fb, seq=200)
    pkts = p.feed(begin_raw)
    assert pkts[0].msg_type == MsgType.FACE_IMAGE_BEGIN
    from packet_protocol import decode_face_image_begin
    r.feed_begin(decode_face_image_begin(pkts[0].payload))

    # 3 chunk × 100 byte JPEG (fake)
    fake_jpeg = bytes(range(256)) * 2  # 512 byte (yeterli)
    fake_jpeg = fake_jpeg[:300]
    done = None
    for i in range(3):
        chunk_data = fake_jpeg[i * 100:(i + 1) * 100]
        payload = struct.pack("<I", 1) + chunk_data
        raw = encode_face_image_chunk(i, 3, payload, seq=201 + i)
        pkts = p.feed(raw)
        for pk in pkts:
            data = pk.payload[4:]
            done = r.feed_chunk(1, pk.chunk, pk.total, data)
    assert done is not None
    fb_out, jpeg = done
    assert len(jpeg) == 300
    assert jpeg == fake_jpeg


def test_sha_tamper_rejected():
    """Payload bytes tamamen değişse bile SHA header ile uyuşmayacağı için
    decrypt'sız modda parser SHA fail döndürmeli. NOT: AES yokken sha hash
    plaintext üzerinden — payload bayt değişirse hem CRC hem SHA fail."""
    req = DeliveryRequest(lat=1.0, lon=2.0, alt=3.0, recipient_id=1,
                          gps_fix=3, num_sats=8)
    raw = bytearray(encode_delivery_request(req, seq=20))
    # CRC alanını da düzeltirsek sadece SHA testi izole olur.
    # Bunu ayrı yapmak için: payload son byte'ı değiştir + CRC yeniden hesapla.
    from packet_protocol import HEADER_SIZE, CRC_SIZE, crc16_ccitt
    payload_start = HEADER_SIZE
    raw[payload_start] ^= 0x55
    new_crc = crc16_ccitt(bytes(raw[2:-CRC_SIZE]))
    raw[-2] = new_crc & 0xFF
    raw[-1] = (new_crc >> 8) & 0xFF
    p = StreamParser()
    out = p.feed(bytes(raw))
    assert out == []
    assert p.sha_errors >= 1


def test_boot_beacon_not_replay_blocked():
    """Boot beacon ardışık iki kez kabul edilmeli (replay'den muaf)."""
    raw = encode_boot_beacon(seq_start=5000, fw_version=2)
    p = StreamParser()
    out1 = p.feed(raw)
    out2 = p.feed(raw)
    assert len(out1) == 1
    assert len(out2) == 1
    assert p.replay_drops == 0
