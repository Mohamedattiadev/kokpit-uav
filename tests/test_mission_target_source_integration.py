"""Uçtan uca görev testi — madde 1+2+4 (yeni sadeleştirilmiş akış).

Hedef GPS artık LoRa'dan DEĞİL, doğrudan Mission(target=...) ile (madde 1);
LoRa hiç kurulmaz/kullanılmaz (madde 2 — yer istasyonu göstermelik); biyometrik
doğrulama varsayılan olarak bypass'lı (madde 4) — StubVerifier'a gerek yok.

Karşılaştır: tests/test_mission_integration.py (eski LoRa enjeksiyonlu yol,
hâlâ geçerli/test edilen bir alternatif giriş noktası).
"""
from __future__ import annotations
import pytest

from config import CFG
from packet_protocol import DeliveryRequest
from aruco_detector import ArucoDetector
from package_dropper import PackageDropper
from mission import Mission
from sim_backend import FakeDrone, SimDownCamera


def _fast_profile():
    CFG.aruco.marker_length_m = 0.5
    CFG.flight.takeoff_altitude_m = 4.0
    CFG.flight.cruise_altitude_m = 8.0
    CFG.flight.search_altitude_m = 6.0
    CFG.flight.drop_altitude_m = 2.5
    CFG.flight.waypoint_accept_radius_m = 1.0
    CFG.pid.descent_speed_ms = 1.0
    CFG.pid.max_z_speed_ms = 1.5
    CFG.safety.overall_mission_timeout_s = 200.0


@pytest.mark.timeout(200)
def test_mission_with_target_source_no_lora_needed():
    _fast_profile()
    drone = FakeDrone(home_lat=39.942000, home_lon=32.847000)
    mlat = drone.home_lat + 15.0 / 111320.0
    mlon = drone.home_lon
    cam = SimDownCamera(drone, mlat, mlon, marker_len_m=CFG.aruco.marker_length_m)
    target = DeliveryRequest(lat=mlat, lon=mlon, alt=900.0, recipient_id=0,
                             gps_fix=3, num_sats=12)
    # lora=None kasıtlı: madde 2 — kritik yol LoRa'ya bağımlı OLMAMALI.
    m = Mission(drone=drone, lora=None, camera=cam,
                detector=ArucoDetector(), dropper=PackageDropper(drone),
                target=target)
    try:
        m.setup()
        ok = m.run()
    finally:
        m.close()
    assert ok, "görev tamamlanmalı"
    assert m.package_delivered, "paket bırakılmalı (biyometrik bypass -> her zaman PASS)"
    # setup() lora=None ise sessizce bir alıcı açar (madde 2: kod silinmedi,
    # sadece kritik yola bağımlı değil) ama hiçbir paket enjekte edilmedi/
    # tüketilmedi — WAIT_PACKET tamamen target üzerinden geçti.
    assert m.lora._delivery_q.empty()
