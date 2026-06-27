"""
Uçtan uca görev entegrasyon testi (yazılım fizik simülasyonu).

FakeDrone (fizik) + SimDownCamera (ArUco render) + SimLoRaReceiver (paket enjekte)
ile tüm pipeline GERÇEK ArUco tespiti ve GERÇEK görsel servo PID üzerinden
kapalı döngü çalıştırılır. ArduPilot SITL gerekmez.

Senaryolar:
  1) Başarılı teslimat: paket bırakılır, görev tamamlanır.
  2) Biyometrik ret: paket BIRAKILMAZ, İHA üsse döner (teslimat askıya alınır).
"""
import math
import pytest

from config import CFG
from packet_protocol import DeliveryRequest
from lora_receiver import SimLoRaReceiver
from aruco_detector import ArucoDetector
from package_dropper import PackageDropper
from face_verifier import VerifyResult
from mission import Mission
from sim_backend import FakeDrone, SimDownCamera


class StubVerifier:
    """Biyometrik doğrulamayı deterministik yapan test stub'ı.
    (Yüz eşleştirme MANTIĞI ayrıca face_verifier birim testlerinde sınanır.)"""
    def __init__(self, result: bool):
        self.result = result
        self.enrolled = [7]

    def load_dataset(self, directory=None):
        return 1

    def verify_with_voting(self, recipient_id, camera, on_frame=None):
        # birkaç kare oku (kamera akışını gerçekçi tüket)
        for _ in range(3):
            camera.read()
        return VerifyResult(matched=self.result,
                            confidence=0.95 if self.result else 0.1,
                            face_found=True, recipient_id=recipient_id)


def _fast_profile():
    """Testi hızlandıran ve marker'ı tespit edilebilir tutan profil."""
    CFG.aruco.marker_length_m = 0.5
    CFG.flight.takeoff_altitude_m = 4.0
    CFG.flight.cruise_altitude_m = 8.0
    CFG.flight.search_altitude_m = 6.0
    CFG.flight.drop_altitude_m = 2.5
    CFG.flight.waypoint_accept_radius_m = 1.0
    CFG.pid.descent_speed_ms = 1.0
    CFG.pid.max_z_speed_ms = 1.5
    CFG.safety.overall_mission_timeout_s = 200.0


def _build(result_match: bool):
    _fast_profile()
    drone = FakeDrone(home_lat=39.942000, home_lon=32.847000)
    # marker'ı home'dan ~15 m kuzeye koy
    mlat = drone.home_lat + 15.0 / 111320.0
    mlon = drone.home_lon
    cam = SimDownCamera(drone, mlat, mlon, marker_len_m=CFG.aruco.marker_length_m)
    lora = SimLoRaReceiver()
    m = Mission(drone=drone, lora=lora, camera=cam,
                detector=ArucoDetector(), verifier=StubVerifier(result_match),
                dropper=PackageDropper(drone))
    # teslimat talebini önceden enjekte et (ped GPS'i = marker konumu)
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900.0, recipient_id=7, gps_fix=3, num_sats=12))
    return m, drone, (mlat, mlon)


@pytest.mark.timeout(200)
def test_successful_delivery():
    m, drone, _ = _build(result_match=True)
    try:
        m.setup()
        ok = m.run()
    finally:
        m.close()
    assert ok, "görev tamamlanmalı"
    assert m.package_delivered, "paket bırakılmalı"
    assert drone.servo_pwm.get(CFG.dropper.servo_channel) is not None
    assert not drone.armed, "görev sonunda disarm olmalı"


@pytest.mark.timeout(200)
def test_biometric_rejection_no_drop():
    m, drone, _ = _build(result_match=False)
    try:
        m.setup()
        ok = m.run()
    finally:
        m.close()
    # İHA güvenle döner; paket BIRAKILMAZ
    assert not m.package_delivered, "eşleşme yoksa paket bırakılmamalı"
    assert not drone.armed
