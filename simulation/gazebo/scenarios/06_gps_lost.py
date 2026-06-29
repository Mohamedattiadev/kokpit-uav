"""Senaryo 6: GPS fix kaybı — LAND."""
from _common import FaultInjection, simulate, ScenarioOutcome


def run() -> ScenarioOutcome:
    return simulate(FaultInjection(gps_fix_type=1, gps_sats=3))


if __name__ == "__main__":
    o = run()
    assert o.land_triggered and o.abort_reason == "GPS_LOST"
    print("OK:", o)
