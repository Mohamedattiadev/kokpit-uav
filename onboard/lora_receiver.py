"""
lora_receiver.py — İHA tarafı LoRa paket alıcısı

Jetson'a bağlı LoRa E32 (UART) üzerinden gelen baytları okur, StreamParser ile
CRC-doğrulanmış paketlere ayırır ve DELIVERY_REQUEST'i çözer (rapor 3.3.1.2).

İki uygulama:
  * SerialLoRaReceiver : gerçek donanım (pyserial).
  * SimLoRaReceiver    : SITL/test — inject_delivery(req) ile paket enjekte edilir.
open_lora() SIMULATION durumuna göre doğru olanı verir.
"""
from __future__ import annotations
import time
import threading
import queue
from typing import Optional

from config import CFG
from packet_protocol import (
    StreamParser, MsgType, decode_delivery_request, DeliveryRequest,
    encode_delivery_request,
)


class BaseLoRaReceiver:
    def __init__(self):
        self.parser = StreamParser()
        self._delivery_q: "queue.Queue[DeliveryRequest]" = queue.Queue()
        self.abort_requested = False

    def _ingest(self, raw: bytes):
        for pkt in self.parser.feed(raw):
            if pkt.msg_type == MsgType.DELIVERY_REQUEST:
                try:
                    req = decode_delivery_request(pkt.payload)
                    self._delivery_q.put(req)
                except ValueError as e:
                    print("[LORA] Çözme hatası:", e)
            elif pkt.msg_type == MsgType.ABORT:
                self.abort_requested = True
                print("[LORA] ABORT paketi alındı")

    def wait_for_delivery(self, timeout: Optional[float] = None
                          ) -> Optional[DeliveryRequest]:
        """Geçerli (GPS fix'li) bir teslimat talebi gelene kadar bekle."""
        start = time.time()
        while timeout is None or (time.time() - start) < timeout:
            try:
                req = self._delivery_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if req.is_valid_fix():
                print(f"[LORA] Teslimat talebi: ({req.lat:.6f}, {req.lon:.6f}) "
                      f"alıcı={req.recipient_id} sat={req.num_sats}")
                return req
            print("[LORA] Geçersiz GPS fix'li paket atlandı")
        return None

    def close(self):
        pass


class SerialLoRaReceiver(BaseLoRaReceiver):
    def __init__(self, port: str, baud: int):
        super().__init__()
        import serial  # pyserial (lazy import)
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
        self.inject_raw(encode_delivery_request(req, seq))
        print(f"[LORA-SIM] Paket enjekte edildi: ({req.lat:.6f},{req.lon:.6f})")


def open_lora() -> BaseLoRaReceiver:
    if CFG.simulation:
        return SimLoRaReceiver()
    return SerialLoRaReceiver(CFG.link.lora_port_real, CFG.link.lora_baud)
