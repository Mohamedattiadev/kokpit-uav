"""Gerçek dünya çoklu-arıza (multi-fault) ve batarya karar testleri.

onboard/mission.py'deki failsafe priority queue (PRIO_*) ve _do_abort karar
mantığını, FakeDrone (sim_backend) üzerinden GERÇEK Mission kodu ile sınar —
sadece izole birim testi değil, gerçek nesne grafiği üzerinden."""
from __future__ import annotations
import time

from config import CFG
from mission import Mission
from sim_backend import FakeDrone


def _mission_with_drone():
    drone = FakeDrone()
    drone.connect()
    m = Mission(drone=drone)
    m.dropper = None
    m.setup()
    return m, drone


def test_battery_critical_lands_in_place_not_rtl():
    """Rapor karar ağacı: 'Pil seviyesi kritik eşiğe düşerse ... en yakın
    güvenli alana in' -> BATTERY_CRT abort RTL DEĞİL, LAND üretmeli
    (mission.py:_do_abort düzeltmesi)."""
    m, drone = _mission_with_drone()
    try:
        drone.armed = True
        m.request_abort("[BATTERY_CRT] Kritik batarya 20.50V")
        m._do_abort()
        assert drone.mode == "LAND", "kritik pilde RTL denemek yerine yerinde inmeli"
    finally:
        m.close()
        drone.close()


def test_battery_low_still_attempts_rtl():
    """BATTERY_LOW (henüz kritik değil) rapor akışında hâlâ RTL'in makul
    olduğu bir seviye — bu davranış değişmemeli (regresyon koruması)."""
    m, drone = _mission_with_drone()
    try:
        drone.armed = True
        m.request_abort("[BATTERY_LOW] Düşük batarya 21.80V")
        m._do_abort()
        assert drone.mode == "RTL"
    finally:
        m.close()
        drone.close()


def test_failsafe_priority_battery_crit_beats_gps_lost_simultaneously():
    """Aynı tick'te hem BATTERY_CRT hem GPS_LOST tetiklenirse, priority queue
    (heapq, PRIO_BATTERY_CRT=90 > PRIO_GPS_LOST=60) BATTERY_CRT'yi seçmeli —
    _consume_failsafes en yüksek öncelikliyi işler, diğerini atar."""
    m, drone = _mission_with_drone()
    try:
        m._push_failsafe(m.PRIO_GPS_LOST, "GPS_LOST", "GPS fix kaybı (fix=0)")
        m._push_failsafe(m.PRIO_BATTERY_CRT, "BATTERY_CRT", "Kritik batarya 20.5V")
        m._consume_failsafes()
        assert m._abort
        assert "BATTERY_CRT" in m._abort_reason, (
            "yüksek öncelikli BATTERY_CRT, GPS_LOST'u ezmeli")
    finally:
        m.close()
        drone.close()


def test_failsafe_priority_link_lost_beats_battery_low_and_geofence():
    """LINK_LOST(80) > BATTERY_LOW(70) > GEOFENCE(30) sırası aynı tick'te
    üç arıza birden geldiğinde korunmalı."""
    m, drone = _mission_with_drone()
    try:
        m._push_failsafe(m.PRIO_GEOFENCE, "GEOFENCE", "Geofence yarıçapı aşıldı")
        m._push_failsafe(m.PRIO_BATTERY_LOW, "BATTERY_LOW", "Düşük batarya 21.8V")
        m._push_failsafe(m.PRIO_LINK_LOST, "LINK_LOST", "MAVLink heartbeat kaybı")
        m._consume_failsafes()
        assert "LINK_LOST" in m._abort_reason
    finally:
        m.close()
        drone.close()


def test_crash_beats_everything_except_user_abort():
    """CRASH(95) sadece USER_ABORT(100)'ün altında — batarya/GPS/link gibi
    tüm diğer arızaları ezmeli (devrilme her zaman en acil müdahale)."""
    m, drone = _mission_with_drone()
    try:
        m._push_failsafe(m.PRIO_BATTERY_CRT, "BATTERY_CRT", "Kritik batarya")
        m._push_failsafe(m.PRIO_LINK_LOST, "LINK_LOST", "Link kaybı")
        m._push_failsafe(m.PRIO_CRASH, "CRASH", "Devrilme: tilt=52°")
        m._consume_failsafes()
        assert "CRASH" in m._abort_reason
    finally:
        m.close()
        drone.close()


def test_failsafe_monitor_detects_battery_low_via_realistic_telemetry():
    """Failsafe monitor thread'i, gerçek FakeDrone telemetrisinden okunan
    battery_voltage'a göre BATTERY_LOW'ı tetikler (uçtan uca, izole değil)."""
    m, drone = _mission_with_drone()
    try:
        drone.armed = True
        drone.battery_voltage = CFG.safety.battery_low_voltage - 0.1
        deadline = time.time() + 3.0
        while time.time() < deadline and not m._abort:
            time.sleep(0.1)
        assert m._abort
        assert "BATTERY_LOW" in m._abort_reason
    finally:
        m.close()
        drone.close()
