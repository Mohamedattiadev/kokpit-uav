"""
test_mission_sitl.py — Görevi GERÇEK ArduPilot SITL'e karşı çalıştırır.

Bu, yazılım-içi fizik testinden (tests/test_mission_integration.py) bir adım
ötesidir: MAVLink komutları GERÇEK ArduCopter SITL fiziğine gönderilir; görüş
(ArUco) ve LoRa simüle edilir. Yani uçuş kontrol davranışı gerçekçidir.

ÖN KOŞUL: Başka bir terminalde SITL çalışıyor olmalı:
    ./run_sitl.sh
Sonra:
    KOKPIT_SIM=1 python3 test_mission_sitl.py

Akış: SITL'e bağlan -> home'u oku -> 20 m kuzeye sanal marker/ped koy ->
teslimat paketini enjekte et -> görevi çalıştır -> sonuçları raporla.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))
os.environ.setdefault("KOKPIT_SIM", "1")

from config import CFG                       # noqa: E402
from mavlink_interface import DroneController  # noqa: E402
from lora_receiver import SimLoRaReceiver    # noqa: E402
from aruco_detector import ArucoDetector     # noqa: E402
from package_dropper import PackageDropper   # noqa: E402
from face_verifier import VerifyResult       # noqa: E402
from packet_protocol import DeliveryRequest  # noqa: E402
from mission import Mission                  # noqa: E402
from sim_backend import SimDownCamera        # noqa: E402


class StubVerifier:
    def __init__(self, result=True):
        self.result = result
        self.enrolled = [7]

    def load_dataset(self, directory=None):
        return 1

    def verify_with_voting(self, recipient_id, camera, on_frame=None):
        for _ in range(3):
            camera.read()
        return VerifyResult(matched=self.result, confidence=0.95,
                            face_found=True, recipient_id=recipient_id)


def main():
    # Marker'ı SITL'de güvenilir tespit için profil ayarı
    CFG.aruco.marker_length_m = 0.6
    CFG.flight.cruise_altitude_m = 12.0
    CFG.flight.search_altitude_m = 8.0
    CFG.flight.drop_altitude_m = 2.5

    drone = DroneController()
    drone.connect()
    # Home/başlangıç konumunu al
    for _ in range(40):
        t = drone.telemetry()
        if t.lat != 0.0:
            break
        time.sleep(0.25)
    home_lat, home_lon = t.lat, t.lon
    print(f"[SITL-TEST] Home: {home_lat:.6f}, {home_lon:.6f}")

    mlat = home_lat + 20.0 / 111320.0   # 20 m kuzey
    mlon = home_lon
    cam = SimDownCamera(drone, mlat, mlon, marker_len_m=CFG.aruco.marker_length_m)
    lora = SimLoRaReceiver()

    m = Mission(drone=drone, lora=lora, camera=cam,
                detector=ArucoDetector(), verifier=StubVerifier(True),
                dropper=PackageDropper(drone))
    m.setup()
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=t.alt_amsl, recipient_id=7,
        gps_fix=3, num_sats=14))

    ok = False
    try:
        ok = m.run()
    finally:
        m.close()

    print("\n================ SITL TEST SONUCU ================")
    print(f" Görev tamam     : {ok}")
    print(f" Paket teslim    : {m.package_delivered}")
    print("==================================================")
    sys.exit(0 if (ok and m.package_delivered) else 1)


if __name__ == "__main__":
    main()
