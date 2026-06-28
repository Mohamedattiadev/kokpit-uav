"""
telemetry_tx.py — Jetson → ESP32 1 Hz TELEMETRY paketi (rapor 3.3.1).

Mode, batarya, mission_phase, RSSI/paket kaybı yer istasyonu TFT'sinde
gösterilir. Gerçek donanım yoksa (serial=None) sadece encode + log.
"""
from __future__ import annotations
import threading
import time
from typing import Callable, Optional

from packet_protocol import encode_telemetry

MODE_MAP = {
    "GUIDED": 1, "AUTO": 2, "LOITER": 3, "RTL": 4, "LAND": 5,
    "STABILIZE": 6, "MANUAL": 7, "BRAKE": 8, "POSHOLD": 9, "UNKNOWN": 0,
}


class TelemetryTx:
    def __init__(self, drone, lora=None, mission=None,
                 send_raw: Optional[Callable[[bytes], None]] = None,
                 hz: float = 1.0):
        self.drone = drone
        self.lora = lora
        self.mission = mission
        self.send_raw = send_raw   # E32 UART write çağırıcı (None → log only)
        self.period_s = 1.0 / hz
        self._running = False
        self._t: Optional[threading.Thread] = None
        self._seq = 0

    def _phase_id(self) -> int:
        if self.mission is None:
            return 0
        try:
            return int(self.mission.fsm.state.value)
        except Exception:
            return 0

    def build_packet(self) -> bytes:
        t = self.drone.telemetry() if self.drone else None
        mode_id = MODE_MAP.get(t.mode if t else "UNKNOWN", 0)
        batt_mv = int((t.battery_voltage * 1000) if t else 0)
        phase = self._phase_id()
        rssi = int(self.lora.last_rssi) if self.lora else 0
        loss = int(self.lora.packet_loss_pct()) if self.lora else 0
        pkt = encode_telemetry(mode_id, batt_mv, phase, rssi, loss,
                               seq=self._seq)
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return pkt

    def tick(self) -> bytes:
        pkt = self.build_packet()
        if self.send_raw:
            try:
                self.send_raw(pkt)
            except Exception as e:
                print(f"[TLM] send hata: {e}")
        return pkt

    def start(self) -> None:
        self._running = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._running = False
        if self._t:
            self._t.join(timeout=2.0)

    def _loop(self) -> None:
        while self._running:
            self.tick()
            time.sleep(self.period_s)
