"""
software_demo.py — Tüm görevi YAZILIM simülasyonunda çalıştırır (kurulum gerekmez).

ArduPilot SITL / Pixhawk / kamera / LoRa OLMADAN, FakeDrone fiziği ve sentetik
ArUco kamerası ile uçtan uca görev akışını gösterir. GERÇEK ArUco tespiti ve
GERÇEK görsel servo PID kullanılır.

Çalıştır:
    KOKPIT_SIM=1 python3 software_demo.py
    KOKPIT_SIM=1 python3 software_demo.py --reject   # biyometrik ret senaryosu
    KOKPIT_SIM=1 python3 software_demo.py --save-video  # logs/demo.mp4 üretir
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))
os.environ.setdefault("KOKPIT_SIM", "1")

import cv2  # noqa: E402
from config import CFG                       # noqa: E402
from lora_receiver import SimLoRaReceiver    # noqa: E402
from aruco_detector import ArucoDetector     # noqa: E402
from package_dropper import PackageDropper   # noqa: E402
from face_verifier import VerifyResult       # noqa: E402
from packet_protocol import DeliveryRequest  # noqa: E402
from mission import Mission                  # noqa: E402
from sim_backend import FakeDrone, SimDownCamera  # noqa: E402


class StubVerifier:
    def __init__(self, result):
        self.result = result
        self.enrolled = [7]

    def load_dataset(self, directory=None):
        return 1

    def verify_with_voting(self, recipient_id, camera, on_frame=None):
        for _ in range(3):
            camera.read()
        return VerifyResult(matched=self.result,
                            confidence=0.95 if self.result else 0.1,
                            face_found=True, recipient_id=recipient_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reject", action="store_true",
                    help="biyometrik doğrulama başarısız senaryosu")
    ap.add_argument("--save-video", action="store_true",
                    help="logs/demo.mp4 olarak kamera kaydı üret")
    args = ap.parse_args()

    # Hızlı + tespit edilebilir profil
    CFG.aruco.marker_length_m = 0.5
    CFG.flight.takeoff_altitude_m = 4.0
    CFG.flight.cruise_altitude_m = 8.0
    CFG.flight.search_altitude_m = 6.0
    CFG.flight.drop_altitude_m = 2.5
    CFG.pid.descent_speed_ms = 1.0
    CFG.pid.max_z_speed_ms = 1.5

    drone = FakeDrone()
    mlat = drone.home_lat + 15.0 / 111320.0
    mlon = drone.home_lon
    cam = SimDownCamera(drone, mlat, mlon, marker_len_m=CFG.aruco.marker_length_m)
    detector = ArucoDetector()
    lora = SimLoRaReceiver()

    writer = None
    if args.save_video:
        os.makedirs("../logs", exist_ok=True)
        writer = cv2.VideoWriter("../logs/demo.mp4",
                                 cv2.VideoWriter_fourcc(*"mp4v"),
                                 15, (CFG.camera.width, CFG.camera.height))

    # Kamera read'i sararak her kareyi anotlayıp videoya yaz
    base_read = cam.read

    def annotated_read():
        ok, frame = base_read()
        det = detector.detect(frame)
        detector.draw(frame, det)
        t = drone.telemetry()
        cv2.putText(frame, f"alt={t.alt_rel:.1f}m mode={t.mode}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        if writer:
            writer.write(frame)
        return ok, frame
    if writer:
        cam.read = annotated_read

    m = Mission(drone=drone, lora=lora, camera=cam, detector=detector,
                verifier=StubVerifier(not args.reject),
                dropper=PackageDropper(drone))
    m.setup()
    lora.inject_delivery(DeliveryRequest(
        lat=mlat, lon=mlon, alt=900.0, recipient_id=7, gps_fix=3, num_sats=12))

    ok = m.run()
    if writer:
        writer.release()
        print("[DEMO] Video: logs/demo.mp4")
    m.close()

    print("\n================ DEMO SONUCU ================")
    print(f" Görev tamam   : {ok}")
    print(f" Paket teslim  : {m.package_delivered}")
    print("=============================================")


if __name__ == "__main__":
    main()
