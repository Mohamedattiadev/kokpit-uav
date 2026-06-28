"""Stress + fuzz + edge testleri — LoRa paket protokolü v2.

Hedef: hatalı/saldırgan/sınır girdilere karşı parser asla crash etmemeli,
sessizce drop etmeli ve sayaçları doğru tutmalı."""
from __future__ import annotations
import os
import random
import struct

import pytest

from packet_protocol import (
    DeliveryRequest, FaceImageBegin,
    StreamParser, ImageReassembler,
    encode_delivery_request, encode_face_image_begin, encode_face_image_chunk,
    encode_abort, encode_boot_beacon, encode_heartbeat,
    decode_delivery_request, decode_face_image_begin,
    crc16_ccitt, MsgType, MAGIC0, MAGIC1, MAX_PAYLOAD, HEADER_SIZE,
)


# ----------------------------- Fuzz: rastgele bayt akışı -----------------------------
@pytest.mark.parametrize("seed", range(10))
def test_random_garbage_never_crashes(seed):
    """100 KB rastgele bayt → parser crash etmemeli, paket bulamamalı."""
    rng = random.Random(seed)
    garbage = bytes(rng.randint(0, 255) for _ in range(100_000))
    p = StreamParser()
    pkts = p.feed(garbage)
    # Eşleşme olursa CRC + SHA çift filtre %99.9 false-positive engeller
    assert len(pkts) <= 1   # nadir doğru-kazara magic+CRC eşleşmesi
    assert p.bytes_dropped > 99_000


@pytest.mark.parametrize("seed", range(20))
def test_bitflip_fuzz_rejects(seed):
    """Geçerli pakete tek-bit flip → parser reject etmeli (CRC veya SHA)."""
    rng = random.Random(seed)
    req = DeliveryRequest(lat=39.9, lon=32.8, alt=900, recipient_id=5,
                          gps_fix=3, num_sats=10)
    raw = bytearray(encode_delivery_request(req, seq=rng.randint(1, 10000)))
    # Magic ve CRC dışındaki rastgele bir bayt flip
    idx = rng.randint(2, len(raw) - 3)
    raw[idx] ^= 1 << rng.randint(0, 7)
    p = StreamParser()
    out = p.feed(bytes(raw))
    # Tek bit flip → CRC neredeyse her zaman fail
    # (eğer plen field'ına denk gelirse "bozuk header" yolu)
    assert (p.crc_errors + p.bytes_dropped) >= 1


def test_split_at_every_byte():
    """Paketi 1-byte chunk'lara böl → her chunk feed sonrası parse OK."""
    req = DeliveryRequest(lat=10.0, lon=20.0, alt=100, recipient_id=1,
                          gps_fix=3, num_sats=9)
    raw = encode_delivery_request(req, seq=500)
    p = StreamParser()
    out = []
    for b in raw:
        out.extend(p.feed(bytes([b])))
    assert len(out) == 1


def test_concatenated_many_packets():
    """100 paket arka arkaya → hepsi parse edilmeli, sıralı."""
    p = StreamParser()
    buf = b""
    for i in range(100):
        req = DeliveryRequest(lat=39 + i * 0.0001, lon=32, alt=900,
                              recipient_id=i % 10, gps_fix=3, num_sats=8)
        buf += encode_delivery_request(req, seq=10000 + i)
    out = p.feed(buf)
    assert len(out) == 100
    # Sıra korundu mu
    for i, pk in enumerate(out):
        got = decode_delivery_request(pk.payload)
        assert got.recipient_id == i % 10


def test_noise_between_packets():
    """Paket + çöp + paket + çöp + paket → 3 paket parse, çöp dropped."""
    a = encode_delivery_request(DeliveryRequest(1, 2, 3, 1, 3, 8), seq=1)
    b = encode_delivery_request(DeliveryRequest(4, 5, 6, 2, 3, 8), seq=2)
    c = encode_delivery_request(DeliveryRequest(7, 8, 9, 3, 3, 8), seq=3)
    noise = b"\xff\x00\xaa\xbb\xcc"
    p = StreamParser()
    out = p.feed(noise + a + noise + b + noise + c + noise)
    assert len(out) == 3
    assert p.bytes_dropped >= 4 * len(noise) - 4   # son noise tüketilmiş olabilir


def test_partial_packet_held_until_complete():
    """Yarım paket → parser tutmalı, geri kalan gelince parse etmeli."""
    req = DeliveryRequest(lat=1, lon=2, alt=3, recipient_id=1, gps_fix=3, num_sats=8)
    raw = encode_delivery_request(req, seq=42)
    p = StreamParser()
    out1 = p.feed(raw[:20])    # sadece header
    assert out1 == []
    out2 = p.feed(raw[20:])
    assert len(out2) == 1


def test_replay_after_many_packets():
    """Replay LRU 256: en eski seq tekrar gelirse kabul edilmeli (evict)."""
    p = StreamParser()
    for i in range(300):
        req = DeliveryRequest(1, 2, 3, 1, 3, 8)
        p.feed(encode_delivery_request(req, seq=i))
    # ilk 44 seq evict edilmiş olmalı (LRU 256)
    out = p.feed(encode_delivery_request(DeliveryRequest(1, 2, 3, 1, 3, 8),
                                          seq=0))
    # LRU full → eski seq tekrar kabul edilir
    assert len(out) == 1
    # Yakın geçmiş seq (örn 299) → hâlâ blocked
    out2 = p.feed(encode_delivery_request(DeliveryRequest(1, 2, 3, 1, 3, 8),
                                           seq=299))
    assert out2 == []
    assert p.replay_drops >= 1


def test_max_payload_packet():
    """MAX_PAYLOAD sınırında paket → kabul edilmeli (just under)."""
    # FACE_IMAGE_CHUNK payload: 4 (img_seq) + N bytes
    big = b"\xab" * (MAX_PAYLOAD - 4)
    payload = struct.pack("<I", 1) + big
    raw = encode_face_image_chunk(0, 1, payload, seq=600)
    p = StreamParser()
    out = p.feed(raw)
    assert len(out) == 1
    assert out[0].payload[4:] == big


def test_oversized_payload_rejected():
    """MAX_PAYLOAD üstü → encode hata vermeli."""
    too_big = b"\x00" * (MAX_PAYLOAD + 1)
    payload = struct.pack("<I", 1) + too_big
    with pytest.raises(ValueError):
        encode_face_image_chunk(0, 1, payload, seq=601)


def test_chunked_image_out_of_order():
    """Chunk'lar tersten gelirse de birleşmeli."""
    r = ImageReassembler()
    fb = FaceImageBegin(lat=1, lon=2, alt=3, gps_fix=3, num_sats=8,
                        jpeg_len=900, jpeg_total_chunks=9, img_seq=7,
                        timestamp_ms=0)
    r.feed_begin(fb)
    fake = bytes(range(256)) * 4
    fake = fake[:900]
    done = None
    indices = list(range(9))
    random.Random(0).shuffle(indices)
    for i in indices:
        d = r.feed_chunk(7, i, 9, fake[i * 100:(i + 1) * 100])
        if d is not None:
            done = d
    assert done is not None
    _, jpeg = done
    assert jpeg == fake


def test_chunked_image_duplicate_chunk():
    """Aynı chunk iki kez gelirse session bozulmamalı."""
    r = ImageReassembler()
    fb = FaceImageBegin(lat=1, lon=2, alt=3, gps_fix=3, num_sats=8,
                        jpeg_len=200, jpeg_total_chunks=2, img_seq=8,
                        timestamp_ms=0)
    r.feed_begin(fb)
    fake = b"A" * 100 + b"B" * 100
    r.feed_chunk(8, 0, 2, b"A" * 100)
    r.feed_chunk(8, 0, 2, b"A" * 100)   # duplicate
    done = r.feed_chunk(8, 1, 2, b"B" * 100)
    assert done is not None
    assert done[1] == fake


def test_chunked_image_missing_begin():
    """BEGIN gelmeden CHUNK → drop, crash yok."""
    r = ImageReassembler()
    done = r.feed_chunk(99, 0, 3, b"X" * 100)
    assert done is None


def test_chunked_image_stale_session_cleanup():
    """Eski session timeout → silinmeli."""
    r = ImageReassembler(timeout_s=0.01)
    fb = FaceImageBegin(lat=1, lon=2, alt=3, gps_fix=3, num_sats=8,
                        jpeg_len=200, jpeg_total_chunks=2, img_seq=10,
                        timestamp_ms=0)
    r.feed_begin(fb)
    import time
    time.sleep(0.05)
    r.cleanup_stale()
    assert 10 not in r._sessions


def test_zero_length_payload():
    """ABORT/HEARTBEAT 0-byte payload → parse OK."""
    p = StreamParser()
    out = p.feed(encode_abort(seq=1) + encode_heartbeat(seq=2))
    assert len(out) == 2
    assert out[0].msg_type == MsgType.ABORT
    assert out[1].msg_type == MsgType.HEARTBEAT


def test_crc_known_vectors_extra():
    """CRC-16/CCITT-FALSE bilinen vektörleri."""
    assert crc16_ccitt(b"") == 0xFFFF
    assert crc16_ccitt(b"\x00") == 0xE1F0
    assert crc16_ccitt(b"123456789") == 0x29B1
    assert crc16_ccitt(b"A" * 1000) != 0


def test_wrong_protocol_version_rejected():
    """v1 paket (eski protokol) v2 parser tarafından reddedilmeli."""
    # Manuel v1-like packet (eski 6-byte header)
    fake_v1 = bytes([0x4B, 0x50, 0x01, 0x01, 0x00, 0x15]) + b"\x00" * 21 + b"\x00\x00"
    p = StreamParser()
    out = p.feed(fake_v1)
    assert out == []   # version mismatch
    assert p.crc_errors >= 1 or p.bytes_dropped >= 1


def test_truncated_packet_after_magic():
    """Magic + 5 byte (header'dan az) → parser tutmalı, daha fazla bekle."""
    p = StreamParser()
    out = p.feed(bytes([MAGIC0, MAGIC1, 0x02, 0x01, 0x00]))
    assert out == []
    # Bytes hâlâ buffer'da, drop yok
    assert p.bytes_dropped == 0


def test_double_magic_in_payload():
    """Payload içinde tesadüfen MAGIC0+MAGIC1 baytları varsa false-trigger yok."""
    # Lat/lon e7 değerlerinde "KP" baytları olabilir
    req = DeliveryRequest(lat=0.0080, lon=0.0080, alt=0, recipient_id=0x504B,
                          gps_fix=3, num_sats=8)
    raw = encode_delivery_request(req, seq=999)
    p = StreamParser()
    out = p.feed(raw)
    assert len(out) == 1   # gerçek paket bulundu


def test_seq_overflow_32bit():
    """seq = 2^32 - 1 (max uint32) → encode OK, decode OK."""
    req = DeliveryRequest(lat=1, lon=2, alt=3, recipient_id=1, gps_fix=3, num_sats=8)
    raw = encode_delivery_request(req, seq=0xFFFFFFFF)
    p = StreamParser()
    out = p.feed(raw)
    assert len(out) == 1
    assert out[0].seq == 0xFFFFFFFF


def test_seq_negative_via_struct_wrapping():
    """Negatif seq Python int → struct wrap → decode'da pozitif olarak görünür.
    (Encode tarafı & 0xFFFFFFFF yapıyor; -1 → 0xFFFFFFFF)."""
    req = DeliveryRequest(1, 2, 3, 1, 3, 8)
    raw = encode_delivery_request(req, seq=-1 & 0xFFFFFFFF)
    p = StreamParser()
    out = p.feed(raw)
    assert len(out) == 1
    assert out[0].seq == 0xFFFFFFFF


def test_sha_mismatch_detected():
    """Payload'ı değiştirip CRC'yi yeniden hesaplarsak SHA fail olmalı."""
    req = DeliveryRequest(lat=1, lon=2, alt=3, recipient_id=1, gps_fix=3, num_sats=8)
    raw = bytearray(encode_delivery_request(req, seq=42))
    # Payload son byte değiştir
    raw[HEADER_SIZE + 5] ^= 0xFF
    # CRC'yi yeniden hesapla ki CRC geçsin, SHA başarısız olsun
    new_crc = crc16_ccitt(bytes(raw[2:-2]))
    raw[-2] = new_crc & 0xFF
    raw[-1] = (new_crc >> 8) & 0xFF
    p = StreamParser()
    out = p.feed(bytes(raw))
    assert out == []
    assert p.sha_errors >= 1


# --------------------------- AES integration (only if cryptography available) ---------------------------

def test_aes_roundtrip_when_key_present(tmp_path, monkeypatch):
    """AES key set → encrypt/decrypt cycle."""
    import importlib
    key_file = tmp_path / "lora.key"
    key_file.write_text("0011223344556677889900aabbccddee")
    monkeypatch.setenv("KOKPIT_LORA_KEY", str(key_file))
    # Modülü yeniden yükle (cipher cache reset)
    import packet_protocol as pp
    importlib.reload(pp)
    req = pp.DeliveryRequest(1, 2, 3, 7, 3, 10)
    raw = pp.encode_delivery_request(req, seq=1)
    p = pp.StreamParser()
    out = p.feed(raw)
    assert len(out) == 1
    got = pp.decode_delivery_request(out[0].payload)
    assert got.recipient_id == 7


def test_aes_wrong_key_rejects(tmp_path, monkeypatch):
    """Yanlış key ile decrypt → drop, crash yok."""
    import importlib
    key1 = tmp_path / "key1"
    key1.write_text("00" * 16)
    monkeypatch.setenv("KOKPIT_LORA_KEY", str(key1))
    import packet_protocol as pp
    importlib.reload(pp)
    req = pp.DeliveryRequest(1, 2, 3, 1, 3, 8)
    raw = pp.encode_delivery_request(req, seq=1)
    # Şimdi farklı key
    key2 = tmp_path / "key2"
    key2.write_text("FF" * 16)
    monkeypatch.setenv("KOKPIT_LORA_KEY", str(key2))
    importlib.reload(pp)
    p = pp.StreamParser()
    out = p.feed(raw)
    assert out == []
    assert p.decrypt_errors >= 1


def test_aes_no_key_falls_back_to_plaintext(tmp_path, monkeypatch):
    """Anahtar yoksa plaintext fallback (geliştirme kolaylığı)."""
    import importlib
    monkeypatch.setenv("KOKPIT_LORA_KEY", str(tmp_path / "nonexistent"))
    import packet_protocol as pp
    importlib.reload(pp)
    req = pp.DeliveryRequest(1, 2, 3, 7, 3, 10)
    raw = pp.encode_delivery_request(req, seq=1)
    p = pp.StreamParser()
    out = p.feed(raw)
    assert len(out) == 1


def test_boot_beacon_resync_after_replay_window():
    """Boot beacon 256 seq sonrası bile kabul edilmeli."""
    p = StreamParser()
    for i in range(500):
        p.feed(encode_delivery_request(DeliveryRequest(1, 2, 3, 1, 3, 8), seq=i))
    # Aynı seq ile boot beacon → kabul edilmeli
    out = p.feed(encode_boot_beacon(seq_start=42, fw_version=2))
    assert len(out) == 1
    assert out[0].msg_type == MsgType.BOOT_BEACON
