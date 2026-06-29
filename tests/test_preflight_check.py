"""N1 — preflight_check kontrol matrisi testleri."""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

# tools/ path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from preflight_check import PreflightCheck, CheckResult  # noqa: E402


def _good_tel():
    return SimpleNamespace(
        fence_enable=1, fence_total=4,
        lidar_ok=True, lidar_last_update=time.time(),
        fix_type=3, satellites=12, hdop=0.8,
        ekf_ok=True, battery_voltage=24.0,
    )


def _bad_tel(**overrides):
    t = _good_tel()
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


def test_all_pass_with_mocks():
    pf = PreflightCheck(
        telemetry_provider=_good_tel,
        camera_fps_provider=lambda: 30.0,
        lora_age_provider=lambda: 0.5,
        face_dataset_count=lambda: 3,
        trt_ready=lambda: True,
        systemd_status=lambda: True,
        require_systemd=True,
    )
    r = pf.run()
    assert r.passed, [(x.name, x.msg) for x in r.results if not x.passed]


def test_geofence_disabled_fails():
    pf = PreflightCheck(telemetry_provider=lambda: _bad_tel(fence_enable=0))
    r = pf.run()
    fence = [x for x in r.results if x.name == "geofence"][0]
    assert not fence.passed
    assert not r.passed


def test_lidar_stale_fails():
    pf = PreflightCheck(
        telemetry_provider=lambda: _bad_tel(lidar_last_update=time.time() - 10),
    )
    r = pf.run()
    lidar = [x for x in r.results if x.name == "lidar"][0]
    assert not lidar.passed


def test_camera_low_fps_fails():
    pf = PreflightCheck(camera_fps_provider=lambda: 10.0)
    r = pf.run()
    cam = [x for x in r.results if x.name == "camera_fps"][0]
    assert not cam.passed


def test_lora_stale_fails():
    pf = PreflightCheck(lora_age_provider=lambda: 30.0)
    r = pf.run()
    lora = [x for x in r.results if x.name == "lora_link"][0]
    assert not lora.passed


def test_gps_low_sats_fails():
    pf = PreflightCheck(telemetry_provider=lambda: _bad_tel(satellites=4))
    r = pf.run()
    gps = [x for x in r.results if x.name == "gps"][0]
    assert not gps.passed


def test_ekf_not_ok_fails():
    pf = PreflightCheck(telemetry_provider=lambda: _bad_tel(ekf_ok=False))
    r = pf.run()
    ekf = [x for x in r.results if x.name == "ekf"][0]
    assert not ekf.passed


def test_battery_low_fails():
    pf = PreflightCheck(telemetry_provider=lambda: _bad_tel(battery_voltage=20.0))
    r = pf.run()
    bat = [x for x in r.results if x.name == "battery"][0]
    assert not bat.passed


def test_face_model_missing_fails():
    pf = PreflightCheck(trt_ready=lambda: False)
    r = pf.run()
    face = [x for x in r.results if x.name == "face_model"][0]
    assert not face.passed


def test_face_dataset_empty_fails():
    pf = PreflightCheck(face_dataset_count=lambda: 0)
    r = pf.run()
    fd = [x for x in r.results if x.name == "face_dataset"][0]
    assert not fd.passed


def test_systemd_required_inactive_fails():
    pf = PreflightCheck(systemd_status=lambda: False, require_systemd=True)
    r = pf.run()
    sd = [x for x in r.results if x.name == "systemd"][0]
    assert not sd.passed


def test_json_report_written(tmp_path):
    pf = PreflightCheck(telemetry_provider=_good_tel)
    r = pf.run()
    p = pf.write_json(r, out_dir=tmp_path)
    assert p.exists()
    data = json.loads(p.read_text())
    assert "results" in data and len(data["results"]) == 12
    assert "passed" in data


def test_param_hash_mismatch_fails(tmp_path):
    fake = tmp_path / "fake.param"
    fake.write_text("FAKE_PARAM=1\n")
    pf = PreflightCheck(param_file=fake, expected_param_hash="deadbeef")
    r = pf.run()
    ph = [x for x in r.results if x.name == "param_hash"][0]
    assert not ph.passed


def test_check_exception_marked_fail():
    def bad_tel():
        raise RuntimeError("simulated")
    pf = PreflightCheck(telemetry_provider=bad_tel)
    r = pf.run()
    # at least one of telemetry-using checks should fail
    fails = [x for x in r.results if not x.passed]
    assert any("exc" in x.msg or "simulated" in x.msg for x in fails)
