"""
time_sync.py — ESP32/Jetson/Pixhawk arası UNIX zaman senkronu.

Görev sonrası log korelasyonu için tüm cihazların aynı UTC tabanlı zaman
damgasını kullanması gerekir. Yaklaşım: MAVLink SYSTEM_TIME (Pixhawk GPS'ten
gelir) dinle, monotonik clock üzerinden offset hesapla. get_synced_unix_us()
güncel monotonik zamanı UNIX µs'e çevirir.

Root yetkisi gerektirmez; gerçek slew için adjtimex opsiyonel.
"""
from __future__ import annotations
import threading
import time

_lock = threading.Lock()
_offset_us: int = 0     # monoton → unix offset (µs)
_have_sync: bool = False
_last_sample_us: int = 0


def _now_mono_us() -> int:
    return int(time.monotonic() * 1_000_000)


def get_synced_unix_us() -> int:
    """Senkronlu UNIX µs döndür. Henüz sync yoksa time.time() düşer."""
    with _lock:
        if _have_sync:
            return _now_mono_us() + _offset_us
    return int(time.time() * 1_000_000)


def is_synced() -> bool:
    with _lock:
        return _have_sync


def offset_us() -> int:
    with _lock:
        return _offset_us


def update_from_system_time(unix_usec: int, mono_us: int | None = None) -> None:
    """MAVLink SYSTEM_TIME (time_unix_usec) geldiğinde çağrılır."""
    global _offset_us, _have_sync, _last_sample_us
    if unix_usec <= 0:
        return
    mono_us = mono_us if mono_us is not None else _now_mono_us()
    with _lock:
        _offset_us = unix_usec - mono_us
        _have_sync = True
        _last_sample_us = mono_us


def reset() -> None:
    """Test için."""
    global _offset_us, _have_sync, _last_sample_us
    with _lock:
        _offset_us = 0
        _have_sync = False
        _last_sample_us = 0


class SystemTimeListener:
    """MAVLink dispatch'inden SYSTEM_TIME mesajlarını time_sync'e gönderir.

    DroneController._handle_msg içine bağlanabilir veya bağımsız thread.
    Hafif: master.recv_match çağırmaz; sadece elle dispatch."""

    def handle(self, msg) -> None:
        if msg is None or msg.get_type() != "SYSTEM_TIME":
            return
        unix_usec = getattr(msg, "time_unix_usec", 0)
        if unix_usec:
            update_from_system_time(int(unix_usec))


def log_with_ts(prefix: str, *parts: str) -> str:
    """Log satırı: '[prefix] ts=<unix_us> ...' formatı."""
    return f"[{prefix}] ts={get_synced_unix_us()} " + " ".join(parts)
