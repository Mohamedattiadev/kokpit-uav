"""
lora_receiver.py — İHA tarafı LoRa paket alıcısı (v2)

Jetson'a bağlı LoRa E32 (UART) üzerinden gelen baytları okur, StreamParser ile
CRC + AES + SHA doğrulanmış paketlere ayırır, FACE_IMAGE_* chunk'larını
ImageReassembler ile birleştirir.

v2 değişiklikleri (Sprint 2 P1.2): FACE_IMAGE_BEGIN + CHUNK desteği.
  * Yeni mod (default): rapor uyumu — yer istasyonu yüz JPEG'ini chunk'lı gönderir.
  * Legacy mod: DELIVERY_REQUEST (recipient_id only) hâlâ kabul edilir.
"""
from __future__ import annotations
import time
import threading
import queue
from dataclasses import dataclass
from typing import Optional

from config import CFG
from packet_protocol import (
    StreamParser, MsgType, Packet,
    DeliveryRequest, FaceImageBegin,
    decode_delivery_request, decode_face_image_begin,
    encode_delivery_request, encode_face_image_begin, encode_face_image_chunk,
    ImageReassembler,
)


@dataclass
class FaceDelivery:
    """Yüz görüntüsü içeren teslimat talebi (yeni mod)."""
    gps: DeliveryRequest      # lat/lon/alt + sats vb.
    jpeg: bytes               # alıcının yüz görüntüsü


class BaseLoRaReceiver:
    def __init__(self):
        self.parser = StreamParser()
        self.reassembler = ImageReassembler()
        self._delivery_q: "queue.Queue" = queue.Queue()
        self.abort_requested = False
        self.peer_seq_start: Optional[int] = None   # BOOT_BEACON'dan
        # M7 — link kalitesi telemetri
        self._rx_window: list[float] = []   # son saniye paket varış zamanları
        self.last_rssi: float = 0.0         # ESP32 desteklerse, opsiyonel
        self.last_packet_seq: Optional[int] = None
        self._expected_seq: Optional[int] = None
        self._received_count: int = 0
        self._missed_count: int = 0

    def _ingest(self, raw: bytes):
        for pkt in self.parser.feed(raw):
            self._handle_packet(pkt)

    def _record_packet_stats(self, pkt: Packet) -> None:
        """Paket varış zamanı + seq tabanlı kayıp istatistikleri."""
        now = time.time()
        self._rx_window.append(now)
        cutoff = now - 1.0
        while self._rx_window and self._rx_window[0] < cutoff:
            self._rx_window.pop(0)
        self._received_count += 1
        seq = getattr(pkt, "seq", None)
        if seq is not None:
            if self._expected_seq is not None and seq > self._expected_seq:
                self._missed_count += (seq - self._expected_seq)
            self._expected_seq = seq + 1
            self.last_packet_seq = seq

    def rx_rate_hz(self) -> float:
        return float(len(self._rx_window))

    def packet_loss_pct(self) -> float:
        tot = self._received_count + self._missed_count
        return 0.0 if tot == 0 else 100.0 * self._missed_count / tot

    def link_stats(self) -> dict:
        return {
            "rx_rate_hz": self.rx_rate_hz(),
            "last_rssi": self.last_rssi,
            "packet_loss_pct": self.packet_loss_pct(),
            "received": self._received_count,
            "missed": self._missed_count,
        }

    def _handle_packet(self, pkt: Packet):
        self._record_packet_stats(pkt)
        if pkt.msg_type == MsgType.BOOT_BEACON:
            # M10 — peer reboot: parser replay LRU yeni seq başlangıcı için reset.
            import struct
            try:
                seq_start, fw = struct.unpack("<II", pkt.payload[:8])
                self.peer_seq_start = seq_start
                self.parser._seen_set.clear()
                self.parser._seen_seqs.clear()
                self._expected_seq = None
                print(f"[LORA] BOOT_BEACON: peer reboot detected, replay "
                      f"window reset (seq_start={seq_start} fw={fw})")
            except Exception:
                pass
        elif pkt.msg_type == MsgType.DELIVERY_REQUEST:
            try:
                req = decode_delivery_request(pkt.payload)
                # Legacy modda jpeg yok, recipient_id ile
                self._delivery_q.put(req)
            except ValueError as e:
                print(f"[LORA] DELIVERY çözme hatası: {e}")
        elif pkt.msg_type == MsgType.FACE_IMAGE_BEGIN:
            try:
                fb = decode_face_image_begin(pkt.payload)
                self.reassembler.feed_begin(fb)
                print(f"[LORA] FACE_IMAGE_BEGIN: img_seq={fb.img_seq} "
                      f"chunks={fb.jpeg_total_chunks} len={fb.jpeg_len}")
            except ValueError as e:
                print(f"[LORA] FACE_BEGIN çözme hatası: {e}")
        elif pkt.msg_type == MsgType.FACE_IMAGE_CHUNK:
            # CHUNK payload: ilk 4 byte img_seq (uint32), kalanı raw bytes
            import struct
            if len(pkt.payload) < 4:
                return
            img_seq = struct.unpack("<I", pkt.payload[:4])[0]
            data = pkt.payload[4:]
            done = self.reassembler.feed_chunk(
                img_seq, pkt.chunk, pkt.total, data)
            if done is not None:
                fb, jpeg = done
                gps = DeliveryRequest(
                    lat=fb.lat, lon=fb.lon, alt=fb.alt,
                    recipient_id=0, gps_fix=fb.gps_fix,
                    num_sats=fb.num_sats, timestamp_ms=fb.timestamp_ms)
                self._delivery_q.put(FaceDelivery(gps=gps, jpeg=jpeg))
                print(f"[LORA] FACE_IMAGE birleştirildi: {len(jpeg)} byte")
        elif pkt.msg_type == MsgType.ABORT:
            self.abort_requested = True
            print("[LORA] ABORT paketi alındı")

    def wait_for_delivery(self, timeout: Optional[float] = None):
        """Geçerli bir teslimat talebi gelene kadar bekle.

        Dönen tip: FaceDelivery (yeni mod) veya DeliveryRequest (legacy)."""
        start = time.time()
        while timeout is None or (time.time() - start) < timeout:
            try:
                item = self._delivery_q.get(timeout=0.5)
            except queue.Empty:
                self.reassembler.cleanup_stale()
                continue
            gps = item.gps if isinstance(item, FaceDelivery) else item
            if gps.is_valid_fix():
                kind = "FACE" if isinstance(item, FaceDelivery) else "LEGACY"
                print(f"[LORA] {kind} teslimat: ({gps.lat:.6f}, {gps.lon:.6f}) "
                      f"sat={gps.num_sats}")
                return item
            print("[LORA] Geçersiz GPS fix'li paket atlandı")
        return None

    def close(self):
        pass


class SerialLoRaReceiver(BaseLoRaReceiver):
    def __init__(self, port: str, baud: int):
        super().__init__()
        import serial
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self._running = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        print(f"[LORA] Seri port açıldı: {port} @ {baud}")

    def _loop(self):
        while self._running:
            data = self.ser.read(256)
            if data:
                self._ingest(data)

    def close(self):
        self._running = False
        try:
            self.ser.close()
        except Exception:
            pass


class SimLoRaReceiver(BaseLoRaReceiver):
    """SITL/test: yer istasyonu yerine paket enjekte edilir."""
    def inject_raw(self, raw: bytes):
        self._ingest(raw)

    def inject_delivery(self, req: DeliveryRequest, seq: int = 0):
        """Legacy yol — recipient_id only."""
        self.inject_raw(encode_delivery_request(req, seq))

    def inject_face_image(self, req: DeliveryRequest, jpeg: bytes,
                          seq_base: int = 0, chunk_payload_size: int = 100):
        """Yeni yol — yüz JPEG'i chunk'lı enjekte et."""
        import math
        import struct
        img_seq = seq_base
        total = max(1, math.ceil(len(jpeg) / chunk_payload_size))
        fb = FaceImageBegin(
            lat=req.lat, lon=req.lon, alt=req.alt,
            gps_fix=req.gps_fix, num_sats=req.num_sats,
            jpeg_len=len(jpeg), jpeg_total_chunks=total,
            img_seq=img_seq, timestamp_ms=req.timestamp_ms)
        self.inject_raw(encode_face_image_begin(fb, seq=seq_base))
        for i in range(total):
            start = i * chunk_payload_size
            chunk_data = jpeg[start:start + chunk_payload_size]
            # Chunk payload: [img_seq:u32] + chunk_data
            payload = struct.pack("<I", img_seq) + chunk_data
            self.inject_raw(encode_face_image_chunk(
                i, total, payload, seq=seq_base + 1 + i))
        print(f"[LORA-SIM] FACE_IMAGE enjekte edildi: {len(jpeg)} byte "
              f"{total} chunk")


def open_lora() -> BaseLoRaReceiver:
    if CFG.simulation:
        return SimLoRaReceiver()
    return SerialLoRaReceiver(CFG.link.lora_port_real, CFG.link.lora_baud)
