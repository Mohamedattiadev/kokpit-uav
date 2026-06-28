"""
packet_protocol.py — Kokpit LoRa paket protokolü (v2)

Yer istasyonu (ESP32) <-> İHA (Jetson) ortak ikili paket biçimi. Aynı bayt
düzeni ESP32 tarafında `firmware/esp32_ground_station/packet_protocol.h`
içinde C struct olarak tanımlanmıştır — değişiklik yapıldığında iki taraf
birlikte güncellenmeli.

v2 Değişiklikleri (Sprint 2 P1.1, P1.2):
  * 32-bit monotonik sequence number (8-bit wrap problemi giderildi).
  * AES-128-CCM şifreleme (opsiyonel: shared/secrets/lora.key varsa kullanılır,
    yoksa plaintext fallback — geliştirme kolaylığı, üretimde key zorunlu).
  * SHA-256 payload bütünlük hash'i (8 byte truncated, header'a eklenir).
  * Yüz görüntüsü chunk'lı iletim: FACE_IMAGE_BEGIN + FACE_IMAGE_CHUNK + END
    ile 160x160 grayscale JPEG (~4 KB) parçalı taşınır. Rapor 3.3.1.1 "FACE
    IMAGE CAPTURE → packet → drone" uyumu için zorunlu.
  * Replay protection: Jetson tarafında LRU son 256 seq tutulur.

Geriye dönük uyum: DELIVERY_REQUEST (recipient_id only) hâlâ destekleniyor,
operatör tercih ederse legacy mod ile çalışılabilir (config.lora.legacy_mode).

Paket Şeması:
  +--------+---------+----------+----------+--------+---------+----------+----------+-------+
  | MAGIC  | VERSION | MSG_TYPE | SEQ_NUM  | CHUNK  | TOT_CHK | SHA8     | PAYLOAD  | CRC16 |
  | 2 byte | 1 byte  | 1 byte   | 4 byte   | 1 byte | 1 byte  | 8 byte   | N byte   | 2 byte|
  +--------+---------+----------+----------+--------+---------+----------+----------+-------+
                                                                <- AES-CCM şifreli ->
"""
from __future__ import annotations
import hashlib
import os
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Optional


# ----------------------------------------------------------------------------
# Sabitler
# ----------------------------------------------------------------------------
MAGIC0 = 0x4B          # 'K'
MAGIC1 = 0x50          # 'P'  -> "KP" = Kokpit
PROTOCOL_VERSION = 2   # v1 -> v2 (AES + 32-bit seq + SHA + image chunking)

HEADER_FMT = "<BBBBIBBH8s"  # m0, m1, ver, msg, seq32, chunk, total, plen, sha8
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 20
CRC_SIZE = 2
MAX_PAYLOAD = 200            # şifrelenmiş payload + tag

AES_KEY_PATH = Path(os.environ.get(
    "KOKPIT_LORA_KEY",
    Path.home() / ".config" / "kokpit" / "lora.key"))
AES_TAG_LEN = 8              # CCM tag
AES_NONCE_LEN = 13           # CCM nonce


class MsgType(IntEnum):
    BOOT_BEACON = 0          # ESP32 boot → seq başlangıç bildirimi
    DELIVERY_REQUEST = 1     # GPS + alıcı kimliği (legacy fallback)
    FACE_IMAGE_BEGIN = 2     # GPS + image meta (chunk_total, jpeg_len)
    FACE_IMAGE_CHUNK = 3     # JPEG raw bytes (chunk_idx ile)
    ABORT = 4                # görev iptal
    HEARTBEAT = 5            # canlılık
    TELEMETRY = 6            # İHA → yer (durum + RSSI)
    ACK = 7                  # paket onayı


# ----------------------------------------------------------------------------
# CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF, no reflect, xorout=0x0000)
# ----------------------------------------------------------------------------
def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


# ----------------------------------------------------------------------------
# AES-128-CCM (opsiyonel; cryptography kurulu değilse plaintext fallback)
# ----------------------------------------------------------------------------
_aes_cipher: Optional["AESCCMCipher"] = None


class AESCCMCipher:
    """AES-128-CCM wrapper. Nonce = seq32 (4) + msg_type (1) + chunk (1) +
    7 byte fixed pad → 13 byte. Reuse riski: seq32 persistent + boot beacon."""

    def __init__(self, key: bytes):
        from cryptography.hazmat.primitives.ciphers.aead import AESCCM
        if len(key) != 16:
            raise ValueError("AES-128 anahtarı 16 byte olmalı")
        self._aes = AESCCM(key, tag_length=AES_TAG_LEN)

    def encrypt(self, plaintext: bytes, seq: int, msg_type: int,
                chunk: int) -> bytes:
        nonce = struct.pack("<IBB7s", seq, msg_type, chunk, b"KOKPIT0")
        return self._aes.encrypt(nonce, plaintext, associated_data=None)

    def decrypt(self, ciphertext: bytes, seq: int, msg_type: int,
                chunk: int) -> bytes:
        nonce = struct.pack("<IBB7s", seq, msg_type, chunk, b"KOKPIT0")
        return self._aes.decrypt(nonce, ciphertext, associated_data=None)


def _load_cipher() -> Optional[AESCCMCipher]:
    global _aes_cipher
    if _aes_cipher is not None:
        return _aes_cipher
    if not AES_KEY_PATH.exists():
        return None
    try:
        key_hex = AES_KEY_PATH.read_text().strip()
        key = bytes.fromhex(key_hex)
        _aes_cipher = AESCCMCipher(key)
        return _aes_cipher
    except Exception as e:
        print(f"[CRYPTO] AES anahtarı yüklenemedi ({e}); plaintext mode")
        return None


# ----------------------------------------------------------------------------
# Veri sınıfları
# ----------------------------------------------------------------------------
@dataclass
class DeliveryRequest:
    lat: float
    lon: float
    alt: float
    recipient_id: int = 0
    gps_fix: int = 3
    num_sats: int = 0
    flags: int = 0
    timestamp_ms: int = 0

    def is_valid_fix(self) -> bool:
        return (self.gps_fix >= 3 and self.num_sats >= 6 and
                -90 <= self.lat <= 90 and -180 <= self.lon <= 180)


@dataclass
class FaceImageBegin:
    """FACE_IMAGE_BEGIN payload: GPS + image meta. Sonrasında jpeg_total_chunks
    adet FACE_IMAGE_CHUNK paketi gelir."""
    lat: float
    lon: float
    alt: float
    gps_fix: int = 3
    num_sats: int = 0
    jpeg_len: int = 0
    jpeg_total_chunks: int = 0
    img_seq: int = 0          # bu görüntü için benzersiz id (chunk korelasyonu)
    timestamp_ms: int = 0


@dataclass
class Packet:
    msg_type: int
    seq: int
    chunk: int
    total: int
    payload: bytes


# Görüntü chunk birleştirici durumu
@dataclass
class _ImageReassembly:
    img_seq: int
    total: int
    chunks: dict = field(default_factory=dict)   # chunk_idx -> bytes
    begin_payload: Optional[FaceImageBegin] = None
    started_at: float = field(default_factory=time.time)


# ----------------------------------------------------------------------------
# DELIVERY_REQUEST payload
# ----------------------------------------------------------------------------
DELIVERY_FMT = "<iiiHBBBI"
DELIVERY_SIZE = struct.calcsize(DELIVERY_FMT)


def _pack_delivery(req: DeliveryRequest) -> bytes:
    return struct.pack(
        DELIVERY_FMT,
        int(round(req.lat * 1e7)),
        int(round(req.lon * 1e7)),
        int(round(req.alt * 1000)),
        req.recipient_id & 0xFFFF,
        req.gps_fix & 0xFF,
        req.num_sats & 0xFF,
        req.flags & 0xFF,
        req.timestamp_ms & 0xFFFFFFFF,
    )


def _unpack_delivery(payload: bytes) -> DeliveryRequest:
    if len(payload) != DELIVERY_SIZE:
        raise ValueError(f"DELIVERY boyutu {len(payload)} != {DELIVERY_SIZE}")
    lat_e7, lon_e7, alt_mm, rid, fix, sats, flags, ts = struct.unpack(
        DELIVERY_FMT, payload)
    return DeliveryRequest(
        lat=lat_e7 / 1e7, lon=lon_e7 / 1e7, alt=alt_mm / 1000.0,
        recipient_id=rid, gps_fix=fix, num_sats=sats, flags=flags,
        timestamp_ms=ts)


# ----------------------------------------------------------------------------
# FACE_IMAGE_BEGIN payload
# ----------------------------------------------------------------------------
FACE_BEGIN_FMT = "<iiiBBHHII"   # lat_e7, lon_e7, alt_mm, fix, sats, jpeg_len,
#                               # total_chunks, img_seq, ts_ms
FACE_BEGIN_SIZE = struct.calcsize(FACE_BEGIN_FMT)


def _pack_face_begin(fb: FaceImageBegin) -> bytes:
    return struct.pack(
        FACE_BEGIN_FMT,
        int(round(fb.lat * 1e7)),
        int(round(fb.lon * 1e7)),
        int(round(fb.alt * 1000)),
        fb.gps_fix & 0xFF,
        fb.num_sats & 0xFF,
        fb.jpeg_len & 0xFFFF,
        fb.jpeg_total_chunks & 0xFFFF,
        fb.img_seq & 0xFFFFFFFF,
        fb.timestamp_ms & 0xFFFFFFFF,
    )


def _unpack_face_begin(payload: bytes) -> FaceImageBegin:
    if len(payload) != FACE_BEGIN_SIZE:
        raise ValueError(f"FACE_BEGIN boyutu {len(payload)} != {FACE_BEGIN_SIZE}")
    lat_e7, lon_e7, alt_mm, fix, sats, jlen, jchunks, iseq, ts = struct.unpack(
        FACE_BEGIN_FMT, payload)
    return FaceImageBegin(
        lat=lat_e7 / 1e7, lon=lon_e7 / 1e7, alt=alt_mm / 1000.0,
        gps_fix=fix, num_sats=sats, jpeg_len=jlen,
        jpeg_total_chunks=jchunks, img_seq=iseq, timestamp_ms=ts)


# ----------------------------------------------------------------------------
# Frame encode / decode
# ----------------------------------------------------------------------------
def _frame(msg_type: int, seq: int, chunk: int, total: int,
           plaintext: bytes) -> bytes:
    cipher = _load_cipher()
    if cipher is not None:
        payload = cipher.encrypt(plaintext, seq, int(msg_type), chunk)
    else:
        payload = plaintext   # plaintext fallback (geliştirme)
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload {len(payload)} > MAX {MAX_PAYLOAD}")
    sha = hashlib.sha256(plaintext).digest()[:8]
    header = struct.pack(HEADER_FMT, MAGIC0, MAGIC1, PROTOCOL_VERSION,
                         int(msg_type) & 0xFF, seq & 0xFFFFFFFF,
                         chunk & 0xFF, total & 0xFF,
                         len(payload) & 0xFFFF, sha)
    crc = crc16_ccitt(header[2:] + payload)
    return header + payload + struct.pack("<H", crc)


def encode_delivery_request(req: DeliveryRequest, seq: int = 0) -> bytes:
    return _frame(MsgType.DELIVERY_REQUEST, seq, 0, 1, _pack_delivery(req))


def encode_face_image_begin(fb: FaceImageBegin, seq: int = 0) -> bytes:
    return _frame(MsgType.FACE_IMAGE_BEGIN, seq, 0, 1, _pack_face_begin(fb))


def encode_face_image_chunk(chunk_idx: int, total: int, data: bytes,
                            seq: int = 0) -> bytes:
    return _frame(MsgType.FACE_IMAGE_CHUNK, seq, chunk_idx, total, data)


def encode_abort(seq: int = 0) -> bytes:
    return _frame(MsgType.ABORT, seq, 0, 1, b"")


def encode_heartbeat(seq: int = 0) -> bytes:
    return _frame(MsgType.HEARTBEAT, seq, 0, 1, b"")


def encode_boot_beacon(seq_start: int, fw_version: int = 1) -> bytes:
    payload = struct.pack("<II", seq_start, fw_version)
    return _frame(MsgType.BOOT_BEACON, seq_start, 0, 1, payload)


def encode_ack(acked_seq: int, status: int = 0, seq: int = 0) -> bytes:
    payload = struct.pack("<IB", acked_seq, status)
    return _frame(MsgType.ACK, seq, 0, 1, payload)


# Telemetry: <mode_id:u8><batt_mV:u16><phase:u8><rssi_dbm:i8><loss_pct:u8>
TELEMETRY_FMT = "<BHBbB"


def encode_telemetry(mode_id: int, batt_mv: int, phase: int,
                     rssi_dbm: int, loss_pct: int, seq: int = 0) -> bytes:
    payload = struct.pack(TELEMETRY_FMT,
                          mode_id & 0xFF, batt_mv & 0xFFFF, phase & 0xFF,
                          max(-128, min(127, rssi_dbm)),
                          max(0, min(100, loss_pct)))
    return _frame(MsgType.TELEMETRY, seq, 0, 1, payload)


def decode_telemetry(payload: bytes) -> tuple[int, int, int, int, int]:
    return struct.unpack(TELEMETRY_FMT, payload[:struct.calcsize(TELEMETRY_FMT)])


def decode_delivery_request(payload: bytes) -> DeliveryRequest:
    return _unpack_delivery(payload)


def decode_face_image_begin(payload: bytes) -> FaceImageBegin:
    return _unpack_face_begin(payload)


# ----------------------------------------------------------------------------
# StreamParser — UART akışından paket ayıkla + AES decrypt + SHA verify +
# replay protection
# ----------------------------------------------------------------------------
class StreamParser:
    def __init__(self) -> None:
        self._buf = bytearray()
        self.crc_errors = 0
        self.bytes_dropped = 0
        self.decrypt_errors = 0
        self.sha_errors = 0
        self.replay_drops = 0
        # Replay LRU
        self._seen_seqs: deque[int] = deque(maxlen=256)
        self._seen_set: set[int] = set()

    def feed(self, data: bytes):
        self._buf.extend(data)
        out = []
        while True:
            pkt = self._try_extract()
            if pkt is None:
                break
            if pkt is False:   # sentinel: parser fail, devam
                continue
            out.append(pkt)
        return out

    def _try_extract(self):
        buf = self._buf
        while len(buf) >= 2 and not (buf[0] == MAGIC0 and buf[1] == MAGIC1):
            buf.pop(0)
            self.bytes_dropped += 1
        if len(buf) < HEADER_SIZE:
            return None
        # Header parse
        try:
            (m0, m1, version, msg_type, seq, chunk, total, plen,
             sha_hdr) = struct.unpack(HEADER_FMT, bytes(buf[:HEADER_SIZE]))
        except struct.error:
            return None
        if plen > MAX_PAYLOAD:
            buf.pop(0)
            self.bytes_dropped += 1
            return False
        frame_len = HEADER_SIZE + plen + CRC_SIZE
        if len(buf) < frame_len:
            return None
        frame = bytes(buf[:frame_len])
        payload_enc = frame[HEADER_SIZE:HEADER_SIZE + plen]
        rx_crc = struct.unpack("<H", frame[-CRC_SIZE:])[0]
        calc_crc = crc16_ccitt(frame[2:HEADER_SIZE + plen])
        if version != PROTOCOL_VERSION or rx_crc != calc_crc:
            buf.pop(0)
            self.bytes_dropped += 1
            self.crc_errors += 1
            return False
        del buf[:frame_len]
        # AES decrypt
        cipher = _load_cipher()
        if cipher is not None:
            try:
                plaintext = cipher.decrypt(payload_enc, seq, msg_type, chunk)
            except Exception:
                self.decrypt_errors += 1
                return False
        else:
            plaintext = payload_enc
        # SHA verify
        sha_calc = hashlib.sha256(plaintext).digest()[:8]
        if sha_calc != sha_hdr:
            self.sha_errors += 1
            return False
        # Replay protection (BOOT_BEACON hariç — resync için)
        if msg_type != int(MsgType.BOOT_BEACON):
            if seq in self._seen_set:
                self.replay_drops += 1
                return False
            self._seen_set.add(seq)
            self._seen_seqs.append(seq)
            if len(self._seen_seqs) == self._seen_seqs.maxlen:
                # LRU eviction
                if len(self._seen_set) > 256:
                    # set'i deque ile senkronize tut
                    self._seen_set = set(self._seen_seqs)
        return Packet(msg_type=msg_type, seq=seq, chunk=chunk,
                      total=total, payload=plaintext)


# ----------------------------------------------------------------------------
# Image reassembler — FACE_IMAGE_BEGIN + N x FACE_IMAGE_CHUNK → tam JPEG
# ----------------------------------------------------------------------------
class ImageReassembler:
    def __init__(self, timeout_s: float = 10.0):
        self.timeout_s = timeout_s
        self._sessions: dict[int, _ImageReassembly] = {}

    def feed_begin(self, fb: FaceImageBegin) -> None:
        self._sessions[fb.img_seq] = _ImageReassembly(
            img_seq=fb.img_seq, total=fb.jpeg_total_chunks, begin_payload=fb)

    def feed_chunk(self, img_seq: int, chunk_idx: int, total: int,
                   data: bytes) -> Optional[tuple[FaceImageBegin, bytes]]:
        sess = self._sessions.get(img_seq)
        if sess is None:
            # BEGIN gelmeden CHUNK geldi — bu paketleri tut ki BEGIN gelince
            # birleştirilsin. Basitlik için drop.
            return None
        sess.chunks[chunk_idx] = data
        if len(sess.chunks) >= sess.total:
            ordered = b"".join(sess.chunks[i] for i in range(sess.total))
            del self._sessions[img_seq]
            return (sess.begin_payload, ordered)
        return None

    def cleanup_stale(self):
        now = time.time()
        for k in list(self._sessions):
            if now - self._sessions[k].started_at > self.timeout_s:
                del self._sessions[k]


if __name__ == "__main__":
    # Roundtrip self-test
    req = DeliveryRequest(lat=39.925533, lon=32.866287, alt=900.0,
                          recipient_id=7, gps_fix=3, num_sats=12,
                          timestamp_ms=123456)
    raw = encode_delivery_request(req, seq=5)
    print(f"DELIVERY paketi: {len(raw)} byte hex: {raw.hex()}")
    p = StreamParser()
    pkts = p.feed(raw)
    assert len(pkts) == 1, pkts
    got = decode_delivery_request(pkts[0].payload)
    assert abs(got.lat - req.lat) < 1e-6 and got.recipient_id == 7
    print(f"OK: CRC errs={p.crc_errors}, drops={p.bytes_dropped}")
