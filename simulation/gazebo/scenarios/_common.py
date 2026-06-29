"""Senaryo orkestrasyonu için ortak yardımcılar.

Her senaryo: fault inject + mock mission run + assert sonuç.
Gerçek SITL+gz yoksa unit-level fault simülasyonu yapılır.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class FaultInjection:
    marker_visible: bool = True
    face_match: bool = True
    link_alive: bool = True
    battery_voltage: float = 24.0
    gps_fix_type: int = 3
    gps_sats: int = 12


@dataclass
class ScenarioOutcome:
    package_delivered: bool = False
    rtl_triggered: bool = False
    land_triggered: bool = False
    abort_reason: str = ""


def simulate(fault: FaultInjection) -> ScenarioOutcome:
    """Failsafe önceliğini taklit et — gerçek SITL yoksa bile davranışı doğrula."""
    out = ScenarioOutcome()
    if not fault.link_alive:
        out.rtl_triggered = True
        out.abort_reason = "LINK_LOST"
        return out
    if fault.battery_voltage < 22.0:
        out.rtl_triggered = True
        out.abort_reason = "BATTERY_LOW"
        return out
    if fault.gps_fix_type < 3 or fault.gps_sats < 8:
        out.land_triggered = True
        out.abort_reason = "GPS_LOST"
        return out
    if not fault.marker_visible:
        out.abort_reason = "MARKER_LOST"
        return out
    if not fault.face_match:
        out.rtl_triggered = True
        out.abort_reason = "FACE_MISMATCH"
        return out
    out.package_delivered = True
    return out
