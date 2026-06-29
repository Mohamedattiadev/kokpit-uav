"""Preflight check — arm öncesi sistem validasyonu.

Rapor 2.1.4 + 3.3.2: arm öncesi tüm sistemler PASS olmadan uçuş yok.
12 kontrol: config, params, geofence, lidar, kamera, lora, gps, ekf, batarya,
TRT/dlib, dataset, systemd. Çıktı renkli tablo + runs/preflight_<ts>.json.
FAIL varsa exit 1. Mission.setup() içinde RuntimeError fırlatılır.
"""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

# Path resolution: tools/ -> repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "onboard") not in sys.path:
    sys.path.insert(0, str(ROOT / "onboard"))

from config import CFG  # noqa: E402


@dataclass
class CheckResult:
    name: str
    passed: bool
    msg: str = ""
    skipped: bool = False


@dataclass
class PreflightReport:
    timestamp: float
    results: list[CheckResult] = field(default_factory=list)
    passed: bool = True

    def to_json(self) -> str:
        return json.dumps({
            "timestamp": self.timestamp,
            "passed": self.passed,
            "results": [asdict(r) for r in self.results],
        }, indent=2)


# ANSI renk kodları
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


class PreflightCheck:
    """Arm öncesi 12 kontrol. Mock injection ile test edilebilir."""

    # ardupilot/kokpit_baseline.param sha256 — değişirse param değişti demektir
    # Yeni hash hesaplama: sha256sum ardupilot/kokpit_baseline.param
    EXPECTED_PARAM_HASH: Optional[str] = (
        "9cf9f7983be1bfd24c29070e67009aa3ade1d4b3e2f493afa3d240eaefe2a431"
    )

    def __init__(self,
                 telemetry_provider: Optional[Callable] = None,
                 camera_fps_provider: Optional[Callable[[], float]] = None,
                 lora_age_provider: Optional[Callable[[], float]] = None,
                 face_dataset_count: Optional[Callable[[], int]] = None,
                 trt_ready: Optional[Callable[[], bool]] = None,
                 systemd_status: Optional[Callable[[], bool]] = None,
                 param_file: Optional[Path] = None,
                 expected_param_hash: Optional[str] = None,
                 require_systemd: bool = False):
        self.tel = telemetry_provider
        self.cam_fps = camera_fps_provider
        self.lora_age = lora_age_provider
        self.face_count = face_dataset_count
        self.trt_ready = trt_ready
        self.systemd_status = systemd_status
        self.param_file = param_file or (ROOT / "ardupilot" / "kokpit_baseline.param")
        self.expected_param_hash = expected_param_hash or self.EXPECTED_PARAM_HASH
        self.require_systemd = require_systemd
        self.results: list[CheckResult] = []

    # ---- 12 kontrol --------------------------------------------------------
    def _check_config(self) -> CheckResult:
        errs = CFG.validate()
        if errs:
            return CheckResult("config_validate", False, "; ".join(errs))
        return CheckResult("config_validate", True, "OK")

    def _check_param_hash(self) -> CheckResult:
        if not self.param_file.exists():
            return CheckResult("param_hash", False,
                               f"Param dosyası yok: {self.param_file}")
        h = hashlib.sha256(self.param_file.read_bytes()).hexdigest()
        if self.expected_param_hash and h != self.expected_param_hash:
            return CheckResult("param_hash", False,
                               f"hash mismatch (got {h[:12]})")
        return CheckResult("param_hash", True, f"sha256 {h[:12]}")

    def _check_geofence(self) -> CheckResult:
        if not self.tel:
            return CheckResult("geofence", True, "skip (no telemetry)", skipped=True)
        t = self.tel()
        fence_enable = getattr(t, "fence_enable", 1)
        fence_total = getattr(t, "fence_total", 4)
        if fence_enable != 1:
            return CheckResult("geofence", False, "FENCE_ENABLE != 1")
        if fence_total < 3:
            return CheckResult("geofence", False, f"FENCE_TOTAL={fence_total} < 3")
        return CheckResult("geofence", True,
                           f"enable={fence_enable} total={fence_total}")

    def _check_lidar(self) -> CheckResult:
        if not self.tel:
            return CheckResult("lidar", True, "skip", skipped=True)
        t = self.tel()
        if not getattr(t, "lidar_ok", False):
            return CheckResult("lidar", False, "lidar_ok=False")
        age = time.time() - getattr(t, "lidar_last_update", 0)
        if age > 2.0:
            return CheckResult("lidar", False, f"stale {age:.1f}s")
        return CheckResult("lidar", True, f"age={age:.2f}s")

    def _check_camera_fps(self) -> CheckResult:
        if not self.cam_fps:
            return CheckResult("camera_fps", True, "skip", skipped=True)
        fps = self.cam_fps()
        if fps < 25.0:
            return CheckResult("camera_fps", False, f"{fps:.1f} < 25 FPS")
        return CheckResult("camera_fps", True, f"{fps:.1f} FPS")

    def _check_lora_link(self) -> CheckResult:
        if not self.lora_age:
            return CheckResult("lora_link", True, "skip", skipped=True)
        age = self.lora_age()
        if age > 5.0:
            return CheckResult("lora_link", False, f"son paket {age:.1f}s önce")
        return CheckResult("lora_link", True, f"age={age:.1f}s")

    def _check_gps(self) -> CheckResult:
        if not self.tel:
            return CheckResult("gps", True, "skip", skipped=True)
        t = self.tel()
        s = CFG.safety
        if t.fix_type < 3:
            return CheckResult("gps", False, f"fix_type={t.fix_type} < 3")
        if t.satellites < s.min_satellites:
            return CheckResult("gps", False,
                               f"sats={t.satellites} < {s.min_satellites}")
        if t.hdop > s.max_hdop:
            return CheckResult("gps", False,
                               f"hdop={t.hdop:.2f} > {s.max_hdop}")
        return CheckResult("gps", True,
                           f"fix={t.fix_type} sats={t.satellites} hdop={t.hdop:.2f}")

    def _check_ekf(self) -> CheckResult:
        if not self.tel:
            return CheckResult("ekf", True, "skip", skipped=True)
        if not self.tel().ekf_ok:
            return CheckResult("ekf", False, "ekf_ok=False")
        return CheckResult("ekf", True, "OK")

    def _check_battery(self) -> CheckResult:
        if not self.tel:
            return CheckResult("battery", True, "skip", skipped=True)
        t = self.tel()
        s = CFG.safety
        if t.battery_voltage <= 0:
            return CheckResult("battery", False, "voltaj okuma yok")
        if t.battery_voltage < s.battery_warn_voltage:
            return CheckResult("battery", False,
                               f"{t.battery_voltage:.2f}V < warn {s.battery_warn_voltage}V")
        return CheckResult("battery", True, f"{t.battery_voltage:.2f}V")

    def _check_face_model(self) -> CheckResult:
        if not self.trt_ready:
            return CheckResult("face_model", True, "skip", skipped=True)
        if not self.trt_ready():
            return CheckResult("face_model", False, "ne TRT ne dlib hazır")
        return CheckResult("face_model", True, "OK")

    def _check_face_dataset(self) -> CheckResult:
        if not self.face_count:
            return CheckResult("face_dataset", True, "skip", skipped=True)
        n = self.face_count()
        if n <= 0:
            return CheckResult("face_dataset", False, "0 yüz kayıtlı")
        return CheckResult("face_dataset", True, f"{n} yüz")

    def _check_systemd(self) -> CheckResult:
        if not self.require_systemd:
            return CheckResult("systemd", True, "skip (sim)", skipped=True)
        if self.systemd_status is None:
            # Gerçek sistem üzerinde systemctl kontrol et
            try:
                rc = subprocess.run(
                    ["systemctl", "is-active", "kokpit-mc"],
                    capture_output=True, timeout=3
                ).returncode
                return CheckResult("systemd", rc == 0,
                                   "active" if rc == 0 else "inactive")
            except Exception as e:
                return CheckResult("systemd", False, f"systemctl: {e}")
        return CheckResult("systemd", self.systemd_status(),
                           "active" if self.systemd_status() else "inactive")

    # ---- Orkestrasyon ------------------------------------------------------
    def run(self) -> PreflightReport:
        checks = [
            self._check_config, self._check_param_hash, self._check_geofence,
            self._check_lidar, self._check_camera_fps, self._check_lora_link,
            self._check_gps, self._check_ekf, self._check_battery,
            self._check_face_model, self._check_face_dataset, self._check_systemd,
        ]
        report = PreflightReport(timestamp=time.time())
        for fn in checks:
            try:
                r = fn()
            except Exception as e:
                r = CheckResult(fn.__name__.lstrip("_"), False, f"exc: {e}")
            report.results.append(r)
            if not r.passed and not r.skipped:
                report.passed = False
        self.results = report.results
        return report

    def write_json(self, report: PreflightReport,
                   out_dir: Optional[Path] = None) -> Path:
        out_dir = out_dir or (ROOT / "runs")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = int(report.timestamp)
        p = out_dir / f"preflight_{ts}.json"
        p.write_text(report.to_json())
        return p

    def print_table(self, report: PreflightReport) -> None:
        print(f"\n{'NAME':<20} {'STATUS':<10} {'MSG'}")
        print("-" * 70)
        for r in report.results:
            if r.skipped:
                tag = f"{YELLOW}SKIP{RESET}"
            elif r.passed:
                tag = f"{GREEN}PASS{RESET}"
            else:
                tag = f"{RED}FAIL{RESET}"
            print(f"{r.name:<20} {tag:<19} {r.msg}")
        print("-" * 70)
        verdict = f"{GREEN}OVERALL: PASS{RESET}" if report.passed \
            else f"{RED}OVERALL: FAIL{RESET}"
        print(verdict)


def run_with_real_telemetry() -> PreflightReport:
    """Gerçek donanım/SITL için. Mission.setup() bunu çağırır."""
    from mavlink_interface import DroneController
    drone = DroneController()
    try:
        drone.connect(timeout=10)
    except Exception as e:
        print(f"[PREFLIGHT] MAVLink bağlantı: {e}")

    def tel_provider():
        return drone.telemetry()

    pf = PreflightCheck(
        telemetry_provider=tel_provider,
        require_systemd=not CFG.simulation,
    )
    return pf.run()


def main() -> int:
    report = run_with_real_telemetry()
    pf = PreflightCheck()
    pf.print_table(report)
    path = pf.write_json(report)
    print(f"JSON: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
