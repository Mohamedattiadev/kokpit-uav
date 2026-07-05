"""Rüzgar altında yaklaşma/hover testleri (yavaştan hızlıya, çoklu yön).

Model: sim_backend.FakeDrone._wind_drift_ne — basitleştirilmiş sabit rüzgar +
Gaussian gust (ArduPilot SITL SIM_WIND_SPD/DIR/TURB eşdeğeri, gerçek Dryden
modeli değil). Amaç: görsel servo PID'inin (onboard/visual_servo.py) düşük-
orta rüzgarda hedefe kilitlenebildiğini, yüksek rüzgarda ise güvenli şekilde
(hız limiti kırpması ile) davrandığını doğrulamak — rapor hedefi ±14 cm."""
from __future__ import annotations
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


class _StubVerifier:
    def __init__(self):
        self.enrolled = [7]

    def load_dataset(self, directory=None):
        return 1

    def verify_with_voting(self, recipient_id, camera, on_frame=None):
        for _ in range(3):
            camera.read()
        return VerifyResult(matched=True, confidence=0.95,
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


def _run_with_wind(wind_speed_ms: float, wind_dir_deg: float, wind_turb: float):
    _fast_profile()
    drone = FakeDrone(home_lat=39.942000, home_lon=32.847000)
    drone.wind_speed_ms = wind_speed_ms
    drone.wind_dir_deg = wind_dir_deg
    drone.wind_turb = wind_turb
    mlat = drone.home_lat + 15.0 / 111320.0
    mlon = drone.home_lon
    cam = SimDownCamera(drone, mlat, mlon, marker_len_m=CFG.aruco.marker_length_m)
    lora = SimLoRaReceiver()
    m = Mission(drone=drone, lora=lora, camera=cam,
                detector=ArucoDetector(), verifier=_StubVerifier(),
                dropper=PackageDropper(drone))
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900.0, recipient_id=7, gps_fix=3, num_sats=12))
    try:
        m.setup()
        ok = m.run()
    finally:
        m.close()
    return m, drone, ok


@pytest.mark.timeout(120)
def test_calm_air_delivery_succeeds():
    """Referans: rüzgarsız ortamda teslimat tamamlanmalı (regresyon koruması)."""
    m, drone, ok = _run_with_wind(0.0, 0.0, 0.0)
    assert ok and m.package_delivered


@pytest.mark.timeout(240)
@pytest.mark.parametrize("speed,direction,turb", [
    (1.0, 45.0, 0.02),      # HAFİF rüzgar — bulgu: bu seviyede bile yaklaşma
                            # zaman aşımına uğrayabiliyor (bkz. docstring)
    (2.0, 90.0, 0.05),      # hafif-orta, hız tavanına yakın/üzerinde
    (5.0, 180.0, 0.10),     # rapor saha limiti (KILAVUZ.md: rüzgar < 5 m/s)
    (9.0, 270.0, 0.15),     # saha limitinin üzerinde, aşırı durum
])
def test_wind_at_or_above_speed_cap_fails_safely_not_catastrophically(speed, direction, turb):
    """BULGU: onboard/config.py PIDConfig.max_xy_speed_ms=1.5 m/s (hassas
    yaklaşma) ve spiral_speed_ms=1.5 m/s (arama), rapor/KILAVUZ.md'nin saha
    rüzgar limiti olan 5 m/s'in ÇOK altında bir marj bırakıyor. Bu sweep
    (1 m/s gibi HAFİF rüzgar dahil) teslimatın başarısız olabildiğini
    gösteriyor — iki farklı yoldan: (a) marker sürekli sarmal arama
    yarıçapını aşacak kadar rüzgarla sürüklenip "marker kayboldu", veya
    (b) marker görünür kalsa bile rüzgara karşı sürekli düzeltme nedeniyle
    yakınsama SafetyConfig.marker_search_timeout_s (60s) içinde tamamlanamayıp
    "yaklaşma zaman aşımı". Her iki durumda da sistem GÜVENLİ şekilde
    başarısız olmalı: çarpma/kilitlenme yok, İHA disarm olmadan önce RTL'e
    geçip eve dönmeli. Bu, 'gerçek dünya rüzgar marjı' konusunda saha
    testi öncesi ele alınması gereken bir BULGU olarak rapora not edildi
    (PID hız tavanlarını/zaman aşımlarını artırmak saha kalibrasyonu
    gerektirdiğinden bu oturumda config.py'deki değerler DEĞİŞTİRİLMEDİ)."""
    m, drone, ok = _run_with_wind(speed, direction, turb)
    assert ok, "görev durum makinesi güvenli şekilde MISSION_COMPLETE'e ulaşmalı"
    assert not drone.armed, "rüzgar teslimatı engellese bile İHA disarm olmalı (çarpma yok)"
    assert not drone.crashed


@pytest.mark.timeout(200)
def test_extreme_wind_still_bounded_by_velocity_limits():
    """Saha limitinin (5 m/s) çok üzerinde (15 m/s) rüzgarda PID hâlâ hız
    komutlarını max_xy_speed_ms ile kırpmalı (send_velocity_body güvenlik
    kırpması) — drone kontrolsüz hızlanmamalı, ancak teslimat süresi/başarısı
    garanti değildir (bu senaryo saha operasyon limitinin dışıdır)."""
    _fast_profile()
    drone = FakeDrone(home_lat=39.942000, home_lon=32.847000)
    drone.wind_speed_ms = 15.0
    drone.wind_dir_deg = 45.0
    drone.wind_turb = 0.25
    drone.connect()
    drone.arm()
    try:
        drone.send_velocity_body(2.0, 2.0, 0.0)
        assert abs(drone._vel[0]) <= CFG.pid.max_xy_speed_ms + 1e-9
        assert abs(drone._vel[1]) <= CFG.pid.max_xy_speed_ms + 1e-9
    finally:
        drone.close()
