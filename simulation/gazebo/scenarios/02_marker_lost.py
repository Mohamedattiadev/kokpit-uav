"""Senaryo 2: marker görünmez — abort (delivered=False)."""
from _common import FaultInjection, simulate, ScenarioOutcome


def run() -> ScenarioOutcome:
    return simulate(FaultInjection(marker_visible=False))


if __name__ == "__main__":
    o = run()
    assert not o.package_delivered
    assert o.abort_reason == "MARKER_LOST"
    print("OK:", o)
