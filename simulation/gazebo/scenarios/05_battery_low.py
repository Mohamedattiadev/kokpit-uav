"""Senaryo 5: batarya kritik — RTL."""
from _common import FaultInjection, simulate, ScenarioOutcome


def run() -> ScenarioOutcome:
    return simulate(FaultInjection(battery_voltage=21.5))


if __name__ == "__main__":
    o = run()
    assert o.rtl_triggered and o.abort_reason == "BATTERY_LOW"
    print("OK:", o)
