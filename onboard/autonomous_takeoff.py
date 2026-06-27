"""
autonomous_takeoff.py — Otonom kalkış (Sorumlu: Zeki Emir)

İHA, yer istasyonundan geçerli veri paketini aldığında bu modül çağrılır.
Akış (rapor 3.1.2 "Kalkış" + 3.3.1.2):
    1) Pre-arm kontrolleri (GPS fix, uydu, HDOP, batarya, EKF, link)
    2) GUIDED moduna geç
    3) ARM
    4) Hedef irtifaya dikey kalkış (VTOL)

Bu adımlardan herhangi biri başarısız olursa False döner ve görev BAŞLAMAZ
(drone düşmesin / yanlış kalkış olmasın).
"""
from __future__ import annotations

from config import CFG
from mavlink_interface import DroneController


def preflight_checks(drone: DroneController) -> tuple[bool, list[str]]:
    """Kalkış öncesi emniyet kontrolleri. (ok, problem_listesi) döner."""
    problems: list[str] = []
    t = drone.telemetry()
    s = CFG.safety

    if not drone.link_alive():
        problems.append("MAVLink heartbeat yok")
    if t.fix_type < 3:
        problems.append(f"GPS 3D fix yok (fix={t.fix_type})")
    if t.satellites < s.min_satellites:
        problems.append(f"Uydu yetersiz ({t.satellites} < {s.min_satellites})")
    if t.hdop > s.max_hdop:
        problems.append(f"HDOP yüksek ({t.hdop:.2f} > {s.max_hdop})")
    if t.battery_voltage > 0 and t.battery_voltage < s.battery_warn_voltage:
        problems.append(f"Batarya düşük ({t.battery_voltage:.1f} V)")
    # EKF: SITL'de bazen geç gelir; sadece uyarı amaçlı (gerçekte zorunlu)
    if not CFG.simulation and not t.ekf_ok:
        problems.append("EKF hazır değil")

    return (len(problems) == 0, problems)


def autonomous_takeoff(drone: DroneController,
                       altitude: float | None = None) -> bool:
    """Tam otonom kalkış dizisi. Başarılıysa True."""
    alt = altitude if altitude is not None else CFG.flight.takeoff_altitude_m
    print("[KALKIŞ] Pre-arm kontrolleri...")

    if not drone.wait_ready_to_arm(timeout=60.0):
        print("[KALKIŞ] İPTAL: arm'a hazır değil")
        return False

    ok, problems = preflight_checks(drone)
    if not ok:
        print("[KALKIŞ] İPTAL — emniyet problemleri:")
        for p in problems:
            print("   -", p)
        return False

    if not drone.set_mode("GUIDED"):
        print("[KALKIŞ] İPTAL: GUIDED moduna geçilemedi")
        return False

    if not drone.arm():
        print("[KALKIŞ] İPTAL: ARM başarısız")
        return False

    print(f"[KALKIŞ] {alt:.1f} m'ye dikey kalkış...")
    if not drone.takeoff(alt):
        print("[KALKIŞ] UYARI: hedef irtifaya tam ulaşılamadı")
        # Yine de hover'da olabiliriz; çağıran karar versin
        return drone.telemetry().alt_rel > alt * 0.5

    print("[KALKIŞ] Başarılı.")
    return True


if __name__ == "__main__":
    # SITL'de tek başına kalkış denemesi
    d = DroneController()
    d.connect()
    try:
        autonomous_takeoff(d)
    finally:
        d.close()
