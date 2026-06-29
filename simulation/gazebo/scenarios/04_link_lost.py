"""Senaryo 4: MAVLink link kaybı — RTL."""
from _common import FaultInjection, simulate, ScenarioOutcome


def run() -> ScenarioOutcome:
    return simulate(FaultInjection(link_alive=False))


if __name__ == "__main__":
    o = run()
    assert o.rtl_triggered and o.abort_reason == "LINK_LOST"
    print("OK:", o)
