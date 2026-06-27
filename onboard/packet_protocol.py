"""
packet_protocol.py — Yer istasyonu (ESP32) <-> İHA (Jetson) LoRa paket protokolü

Bu modül HEM yer istasyonu HEM drone tarafından kullanılan ikili (binary) paket
biçimini tanımlar. Aynı bayt düzeni ESP32 tarafında `firmware/esp32_ground_station/packet_protocol.h`
içinde C struct olarak yeniden tanımlanmıştır — ikisi senkron tutulmalıdır.

Tasarım ilkeleri:
  * Küçük: LoRa E32 (~ birkaç kbps) bant genişliği dardır. Teslimat talebi paketi
    sadece 29 bayttır (6 başlık + 21 gövde + 2 CRC; yüz görüntüsü gönderilmez).
  * Güvenilir: CRC-16/CCITT-FALSE ile bit-seviyesi bütünlük (rapordaki
    "CRC VERIFICATION" adımı).
  * Akış-dostu: Senkron baytı (magic) ile gürültülü UART akışında paket başı bulunur.

NOT (biyometrik veri): Tam yüz JPEG'ini LoRa üzerinden göndermek pratik değildir
(saniyeler sürer). Bunun yerine iki sağlam yöntem desteklenir:
  1) RECIPIENT_ID  : İHA üzerinde kayıtlı yüz veri seti (faces/) bulunur; yer
     istasyonu sadece yetkili alıcının kimliğini gönderir. İHA hedefte kameradan
     gördüğü yüzü bu kimliğin referans fotoğrafıyla eşleştirir. (ÖNERİLEN)
  2) FACE_CHUNK    : Küçük bir gri thumbnail (örn. 64x64 JPEG) parça parça
     gönderilebilir (opsiyonel, yavaş). Protokol bunu da destekler.
"""
from __future__ import annotations
import struct
from dataclasses import dataclass
from enum import IntEnum

# ----------------------------------------------------------------------------
# Sabitler
# ----------------------------------------------------------------------------
MAGIC0 = 0x4B  # 'K'
MAGIC1 = 0x50  # 'P'   -> "KP" = Kokpit
PROTOCOL_VERSION = 1

HEADER_FMT = "<BBBBBB"   # magic0, magic1, version, msg_type, seq, payload_len
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 6
CRC_SIZE = 2
MAX_PAYLOAD = 200


class MsgType(IntEnum):
    DELIVERY_REQUEST = 1   # GPS + alıcı kimliği -> görevi başlat
    FACE_CHUNK = 2         # opsiyonel thumbnail parçası
    ABORT = 3              # görevi iptal et / acil dur
    HEARTBEAT = 4          # yer istasyonu canlılık sinyali


# DELIVERY_REQUEST gövdesi: lat_e7, lon_e7, alt_mm, recipient_id, gps_fix,
#                            num_sats, flags, timestamp_ms
DELIVERY_FMT = "<iiiHBBBI"
DELIVERY_SIZE = struct.calcsize(DELIVERY_FMT)   # 21


# ----------------------------------------------------------------------------
# CRC-16/CCITT-FALSE  (poly=0x1021, init=0xFFFF, no reflect, xorout=0x0000)
# ESP32 tarafındaki crc16_ccitt() ile birebir aynı olmalı.
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
# Veri sınıfları
# ----------------------------------------------------------------------------
@dataclass
class DeliveryRequest:
    lat: float          # derece
    lon: float          # derece
    alt: float          # metre (AMSL; İHA kendi seyir irtifasını kullanır)
    recipient_id: int   # yetkili alıcı kimliği (faces/ ile eşleşir)
    gps_fix: int = 3    # 3 = 3D fix
    num_sats: int = 0
    flags: int = 0
    timestamp_ms: int = 0

    def is_valid_fix(self) -> bool:
        return self.gps_fix >= 3 and self.num_sats >= 6 and \
            -90 <= self.lat <= 90 and -180 <= self.lon <= 180


@dataclass
class Packet:
    msg_type: int
    seq: int
    payload: bytes


# ----------------------------------------------------------------------------
# Kodlama (encode)
# ----------------------------------------------------------------------------
def _frame(msg_type: int, seq: int, payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload çok büyük")
    header = struct.pack(HEADER_FMT, MAGIC0, MAGIC1, PROTOCOL_VERSION,
                         int(msg_type), seq & 0xFF, len(payload))
    # CRC: magic hariç başlık (version..payload_len) + payload üzerinden
    crc = crc16_ccitt(header[2:] + payload)
    return header + payload + struct.pack("<H", crc)


def encode_delivery_request(req: DeliveryRequest, seq: int = 0) -> bytes:
    payload = struct.pack(
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
    return _frame(MsgType.DELIVERY_REQUEST, seq, payload)


def encode_abort(seq: int = 0) -> bytes:
    return _frame(MsgType.ABORT, seq, b"")


def encode_heartbeat(seq: int = 0) -> bytes:
    return _frame(MsgType.HEARTBEAT, seq, b"")


def encode_face_chunk(chunk_index: int, total_chunks: int,
                      data: bytes, seq: int = 0) -> bytes:
    payload = struct.pack("<BB", chunk_index & 0xFF, total_chunks & 0xFF) + data
    return _frame(MsgType.FACE_CHUNK, seq, payload)


# ----------------------------------------------------------------------------
# Çözme (decode)
# ----------------------------------------------------------------------------
def decode_delivery_request(payload: bytes) -> DeliveryRequest:
    if len(payload) != DELIVERY_SIZE:
        raise ValueError(f"DELIVERY_REQUEST boyutu {len(payload)} != {DELIVERY_SIZE}")
    lat_e7, lon_e7, alt_mm, rid, fix, sats, flags, ts = struct.unpack(
        DELIVERY_FMT, payload)
    return DeliveryRequest(
        lat=lat_e7 / 1e7, lon=lon_e7 / 1e7, alt=alt_mm / 1000.0,
        recipient_id=rid, gps_fix=fix, num_sats=sats, flags=flags,
        timestamp_ms=ts,
    )


class StreamParser:
    """Gürültülü UART akışından paket ayıklar.

    Kullanım:
        parser = StreamParser()
        for pkt in parser.feed(serial.read(n)):
            ...  # her pkt CRC-doğrulanmış bir Packet'tir
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.crc_errors = 0
        self.bytes_dropped = 0

    def feed(self, data: bytes):
        self._buf.extend(data)
        out = []
        while True:
            pkt = self._try_extract()
            if pkt is None:
                break
            out.append(pkt)
        return out

    def _try_extract(self):
        buf = self._buf
        # 1) Magic'e hizala
        while len(buf) >= 2 and not (buf[0] == MAGIC0 and buf[1] == MAGIC1):
            buf.pop(0)
            self.bytes_dropped += 1
        if len(buf) < HEADER_SIZE:
            return None
        version = buf[2]
        msg_type = buf[3]
        seq = buf[4]
        payload_len = buf[5]
        total = HEADER_SIZE + payload_len + CRC_SIZE
        if payload_len > MAX_PAYLOAD:
            # bozuk başlık -> 1 bayt at, yeniden senkronize ol
            buf.pop(0)
            self.bytes_dropped += 1
            return None
        if len(buf) < total:
            return None  # paketin tamamı gelmedi
        frame = bytes(buf[:total])
        payload = frame[HEADER_SIZE:HEADER_SIZE + payload_len]
        rx_crc = struct.unpack("<H", frame[HEADER_SIZE + payload_len:total])[0]
        calc_crc = crc16_ccitt(frame[2:HEADER_SIZE + payload_len])
        del buf[:total]
        if version != PROTOCOL_VERSION or rx_crc != calc_crc:
            self.crc_errors += 1
            return None
        return Packet(msg_type=msg_type, seq=seq, payload=payload)


if __name__ == "__main__":
    # Hızlı kendini-test (roundtrip)
    req = DeliveryRequest(lat=39.925533, lon=32.866287, alt=900.0,
                          recipient_id=7, gps_fix=3, num_sats=12,
                          timestamp_ms=123456)
    raw = encode_delivery_request(req, seq=5)
    print("Paket boyutu:", len(raw), "bayt  hex:", raw.hex())
    p = StreamParser()
    # Araya gürültü ekleyip akış ayrıştırmayı test et
    pkts = p.feed(b"\x00\xFF" + raw[:3]) + p.feed(raw[3:] + b"\x11")
    assert len(pkts) == 1, pkts
    got = decode_delivery_request(pkts[0].payload)
    print("Çözülen:", got)
    assert abs(got.lat - req.lat) < 1e-6
    assert got.recipient_id == 7
    print("CRC hataları:", p.crc_errors, "atılan bayt:", p.bytes_dropped)
    print("OK")
