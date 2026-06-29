"""Senaryo 3: face mismatch — RTL trigger, paket teslim edilmez."""
from _common import FaultInjection, simulate, ScenarioOutcome


def run() -> ScenarioOutcome:
    return simulate(FaultInjection(face_match=False))


if __name__ == "__main__":
    o = run()
    assert o.rtl_triggered and not o.package_delivered
    print("OK:", o)
