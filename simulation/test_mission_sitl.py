"""
test_mission_sitl.py — Görevi GERÇEK ArduPilot SITL'e karşı çalıştırır.

Bu, yazılım-içi fizik testinden (tests/test_mission_integration.py) bir adım
ötesidir: MAVLink komutları GERÇEK ArduCopter SITL fiziğine gönderilir; sadece
görüş (ArUco) simüle edilir. Yani uçuş kontrol davranışı gerçekçidir.

Görev sadeleştirme oturumu (madde 1+2+4) güncellemesi: hedef artık LoRa
enjeksiyonu yerine doğrudan Mission(target=...) ile veriliyor; biyometrik
doğrulama Mission'ın varsayılan bypass'lı FaceVerifier'ı üzerinden geçiyor
(StubVerifier'a gerek kalmadı — gerçek üretim kod yolu test ediliyor).

ÖN KOŞUL: Başka bir terminalde SITL çalışıyor olmalı:
    ./run_sitl.sh
Sonra:
    KOKPIT_SIM=1 python3 test_mission_sitl.py

Akış: SITL'e bağlan -> home'u oku -> 20 m kuzeye sanal marker/ped koy ->
hedefi Mission'a doğrudan ver -> görevi çalıştır -> sonuçları raporla.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))
os.environ.setdefault("KOKPIT_SIM", "1")

from config import CFG                       # noqa: E402
from mavlink_interface import DroneController  # noqa: E402
from aruco_detector import ArucoDetector     # noqa: E402
from package_dropper import PackageDropper   # noqa: E402
from packet_protocol import DeliveryRequest  # noqa: E402
from mission import Mission                  # noqa: E402
from sim_backend import SimDownCamera        # noqa: E402


def main():
    # Marker'ı SITL'de güvenilir tespit için profil ayarı
    CFG.aruco.marker_length_m = 0.6
    CFG.flight.cruise_altitude_m = 12.0
    CFG.flight.search_altitude_m = 8.0
    CFG.flight.drop_altitude_m = 2.5
    # ArduPilot SITL'in MultiCopter fizik modeli SIM_BATT_VOLTAGE'ı onurlandırmaz
    # (bkz. libraries/SITL/SIM_Aircraft.cpp update_battery yorumu); BATTERY_STATUS
    # her zaman ~12.6V (3S sabit) raporlar. Gerçek donanım eşiği (6S, 21.0V) burada
    # anlamsız olur; sadece bu SITL koşusu için simülatöre uygun eşik kullan.
    # Üç eşik de (prearm warn / in-flight RTL low / in-flight LAND critical)
    # override edilir ki SITL'in sahte 12.6V'u hiçbirini yanlışlıkla tetiklemesin.
    CFG.safety.battery_warn_voltage = 5.0
    CFG.safety.battery_low_voltage = 5.0
    CFG.safety.battery_critical_voltage = 4.0

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
    # Madde 1: hedef bilgisayardan doğrudan verilir (LoRa YOK).
    target = DeliveryRequest(lat=mlat, lon=mlon, alt=t.alt_amsl,
                             recipient_id=0, gps_fix=3, num_sats=14)

    m = Mission(drone=drone, lora=None, camera=cam,
                detector=ArucoDetector(), dropper=PackageDropper(drone),
                target=target)
    m.setup()

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
