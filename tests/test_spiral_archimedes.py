"""M12 — Arşimet sarmal trajektori geometrisi."""
from __future__ import annotations
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from visual_servo import PrecisionApproach  # noqa: E402


def test_traj_starts_near_origin():
    pts = PrecisionApproach.archimedes_trajectory(step_m=1.0, max_radius_m=5.0)
    assert math.hypot(pts[0][0], pts[0][1]) < 0.5


def test_traj_monotonic_radius():
    pts = PrecisionApproach.archimedes_trajectory(step_m=1.0, max_radius_m=5.0)
    radii = [math.hypot(x, y) for x, y in pts]
    # büyük çoğunluk monoton artan
    inc = sum(1 for i in range(1, len(radii)) if radii[i] >= radii[i - 1] - 1e-6)
    assert inc / len(radii) > 0.95


def test_traj_respects_max_radius():
    pts = PrecisionApproach.archimedes_trajectory(step_m=1.0, max_radius_m=3.0)
    for x, y in pts:
        assert math.hypot(x, y) <= 3.0 + 1e-6


def test_traj_density_increases_with_smaller_step():
    fewer = PrecisionApproach.archimedes_trajectory(step_m=2.0, max_radius_m=5.0)
    more = PrecisionApproach.archimedes_trajectory(step_m=0.5, max_radius_m=5.0)
    assert len(more) > len(fewer)
