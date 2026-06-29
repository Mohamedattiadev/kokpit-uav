"""N2 — Gazebo SITL senaryoları. `gz` yoksa pytest graceful skip."""
from __future__ import annotations
import shutil
from dataclasses import dataclass


def gazebo_available() -> bool:
    return shutil.which("gz") is not None or shutil.which("gazebo") is not None


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    detail: str = ""
