"""Senaryo 1: happy path — tüm sistemler nominal, paket teslim."""
from _common import FaultInjection, simulate, ScenarioOutcome


def run() -> ScenarioOutcome:
    return simulate(FaultInjection())


if __name__ == "__main__":
    o = run()
    assert o.package_delivered, o
    print("OK:", o)
