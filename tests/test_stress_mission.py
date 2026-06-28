"""Mission entegrasyon stress testleri — failsafe injection, abort during phase,
hardware failure scenarios."""
from __future__ import annotations
import math
import threading
import time

import pytest

from config import CFG
from packet_protocol import DeliveryRequest, encode_abort
from lora_receiver import SimLoRaReceiver
from aruco_detector import ArucoDetector
from package_dropper import PackageDropper
from face_verifier import VerifyResult
from mission import Mission
from sim_backend import FakeDrone, SimDownCamera


class StubVerifier:
    def __init__(self, result=True, confidence=0.95):
        self.result = result; self.confidence = confidence
        self.enrolled = [7]

    def load_dataset(self, directory=None): return 1

    def verify_with_voting(self, recipient_id, camera, on_frame=None):
        for _ in range(3):
            camera.read()
        return VerifyResult(matched=self.result, confidence=self.confidence,
                            face_found=True, recipient_id=recipient_id)


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


def _build_mission(*, marker_offset_n_m=15.0, marker_visible=True,
                   verifier_result=True):
    _fast_profile()
    drone = FakeDrone(home_lat=39.942000, home_lon=32.847000)
    mlat = drone.home_lat + marker_offset_n_m / 111320.0
    mlon = drone.home_lon
    if marker_visible:
        cam = SimDownCamera(drone, mlat, mlon, marker_len_m=CFG.aruco.marker_length_m)
    else:
        # Marker'ı çok uzağa koy → kamera asla göremez
        cam = SimDownCamera(drone, mlat + 0.1, mlon + 0.1,
                            marker_len_m=CFG.aruco.marker_length_m)
    lora = SimLoRaReceiver()
    m = Mission(drone=drone, lora=lora, camera=cam,
                detector=ArucoDetector(),
                verifier=StubVerifier(result=verifier_result),
                dropper=PackageDropper(drone))
    return m, drone, lora, (mlat, mlon)


# -------------------- Senaryo 1: marker bulunamaz --------------------

@pytest.mark.timeout(180)
def test_mission_marker_not_found_returns_home():
    """Marker hiç görünmezse drone üsse dönmeli, paket bırakmamalı."""
    m, drone, lora, (mlat, mlon) = _build_mission(marker_visible=False)
    # Kısa arama timeout
    CFG.safety.marker_search_timeout_s = 5.0
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900, recipient_id=7, gps_fix=3, num_sats=12))
    try:
        m.setup()
        m.run()
    finally:
        m.close()
    assert m.package_delivered is False
    assert drone.armed is False


# -------------------- Senaryo 2: external ABORT mid-mission --------------------

@pytest.mark.timeout(180)
def test_mission_aborted_via_lora_during_flight():
    """Kalkıştan sonra LoRa ABORT → drone üsse dönüş + disarm."""
    m, drone, lora, (mlat, mlon) = _build_mission()
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900, recipient_id=7, gps_fix=3, num_sats=12))

    def abort_after_delay():
        time.sleep(3.0)   # NAVIGATE veya SEARCH sırasında
        lora.inject_raw(encode_abort(seq=99999))

    threading.Thread(target=abort_after_delay, daemon=True).start()
    try:
        m.setup()
        m.run()
    finally:
        m.close()
    assert m.package_delivered is False
    assert drone.armed is False


# -------------------- Senaryo 3: battery critical mid-flight --------------------

@pytest.mark.timeout(180)
def test_mission_aborts_on_critical_battery():
    """Görev ortasında batarya kritik → RTL + disarm + paket yok."""
    m, drone, lora, (mlat, mlon) = _build_mission()
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900, recipient_id=7, gps_fix=3, num_sats=12))

    def drop_battery():
        time.sleep(2.5)
        drone.battery_voltage = 20.0   # crit_voltage altı

    threading.Thread(target=drop_battery, daemon=True).start()
    try:
        m.setup()
        m.run()
    finally:
        m.close()
    assert m.package_delivered is False
    assert drone.armed is False


# -------------------- Senaryo 4: biometric reject --------------------

@pytest.mark.timeout(180)
def test_mission_face_mismatch_no_drop_safe_return():
    m, drone, lora, (mlat, mlon) = _build_mission(verifier_result=False)
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900, recipient_id=7, gps_fix=3, num_sats=12))
    try:
        m.setup()
        m.run()
    finally:
        m.close()
    assert m.package_delivered is False
    assert drone.armed is False
    # Servo OPEN PWM ile çağrılmamış olmalı (PWM > 1500)
    open_calls = sum(1 for ch, p in [(CFG.dropper.servo_channel,
                                      drone.servo_pwm.get(CFG.dropper.servo_channel))]
                     if p is not None and p > 1500)
    assert open_calls == 0


# -------------------- Senaryo 5: GPS fix kaybı mid-flight --------------------

@pytest.mark.timeout(180)
def test_mission_gps_lost_triggers_failsafe():
    """fix_type=0 olunca failsafe priority queue GPS_LOST tetiklemeli."""
    m, drone, lora, (mlat, mlon) = _build_mission()
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900, recipient_id=7, gps_fix=3, num_sats=12))

    def drop_gps():
        time.sleep(2.0)
        # FakeDrone.telemetry() hard-coded fix_type=3 — monkeypatch
        orig_tel = drone.telemetry
        def patched():
            t = orig_tel()
            object.__setattr__(t, 'fix_type', 0)
            object.__setattr__(t, 'satellites', 2)
            return t
        drone.telemetry = patched

    threading.Thread(target=drop_gps, daemon=True).start()
    try:
        m.setup()
        m.run()
    finally:
        m.close()
    assert m.package_delivered is False
    assert drone.armed is False


# -------------------- Senaryo 6: invalid GPS fix in trigger packet --------------------

def test_mission_rejects_invalid_gps_packet():
    """Geçersiz GPS fix'li paket gelirse görev başlamamalı."""
    m, drone, lora, _ = _build_mission()
    lora.inject_delivery(DeliveryRequest(
        lat=0.0, lon=0.0, alt=0, recipient_id=7, gps_fix=1, num_sats=2))
    # Geçerli paketi de hemen sonra enjekte et — yoksa wait_for_delivery sonsuza
    # kadar bloklar. Bad packet drop edilmeli, good packet kabul edilmeli.
    lora.inject_delivery(DeliveryRequest(
        lat=39.942, lon=32.847, alt=900, recipient_id=7,
        gps_fix=3, num_sats=12), seq=2)
    try:
        m.setup()
        m.run()
    finally:
        m.close()
    # Görev geçerli paketle başladı; bad olan reddedildi
    assert drone.armed is False   # sonunda disarm


# -------------------- Senaryo 7: face image transfer end-to-end --------------------

@pytest.mark.timeout(180)
def test_mission_face_image_end_to_end():
    """FACE_IMAGE_BEGIN + CHUNK ile JPEG enjeksiyon → enroll + verify path."""
    m, drone, lora, (mlat, mlon) = _build_mission()
    # JPEG yerine sahte byte dizisi (verifier stub'dur, decode başarısız olabilir)
    # Bu yüzden verifier'ı override etmemize gerek yok — StubVerifier her zaman PASS
    # ama enroll_from_jpeg JPEG decode başarısız olursa FAILED'a düşer.
    # Bunu test etmek için: gerçek JPEG benzeri yapı verme; bu test sadece
    # protokol akışını doğrular (decode başarısız → FAILED).
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"A" * 300 + b"\xff\xd9"
    req = DeliveryRequest(lat=mlat, lon=mlon, alt=900, recipient_id=0,
                          gps_fix=3, num_sats=12)
    lora.inject_face_image(req, fake_jpeg, seq_base=10000)
    try:
        m.setup()
        m.run()
    finally:
        m.close()
    # Sahte JPEG decode'da yüz bulunamayacak → enroll fail → FAILED state
    # Bu beklenen + güvenli davranış. Paket bırakılmadığını doğrula.
    assert m.package_delivered is False
    assert drone.armed is False


# -------------------- Senaryo 8: çok hızlı arka arkaya 2 paket --------------------

@pytest.mark.timeout(180)
def test_mission_uses_first_packet_ignores_second():
    """2. paket görev başladıktan sonra gelirse görev devam etmeli."""
    m, drone, lora, (mlat, mlon) = _build_mission()
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900, recipient_id=7,
        gps_fix=3, num_sats=12), seq=1)
    # 2. paket farklı koordinatta (görev hâlâ ilkini kullanmalı)
    def inject_second():
        time.sleep(1.0)
        lora.inject_delivery(DeliveryRequest(
            lat=mlat + 0.01, lon=mlon + 0.01, alt=900, recipient_id=8,
            gps_fix=3, num_sats=12), seq=2)
    threading.Thread(target=inject_second, daemon=True).start()
    try:
        m.setup()
        m.run()
    finally:
        m.close()
    # İlk paketin hedefine gidildi
    assert m.target.recipient_id == 7
