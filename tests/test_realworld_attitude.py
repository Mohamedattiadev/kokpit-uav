"""Attitude/rotation aşırılık testleri — devrilme (crash) tespiti.

onboard/mission.py failsafe monitor'ü |roll|>45° veya |pitch|>45° durumunun
3 ardışık örnekte sürmesi (tilt_count>=3) YA DA 3 ardışık ivme sıçraması
(accel_spike_count>=3) durumunda PRIO_CRASH failsafe'i tetikler ve
force_disarm + servo lock uygular (Sprint 1 P0.1, rapor "Safety First").

Bu testler FakeDrone (sim_backend) üzerinden GERÇEK Mission kodu ile roll/
pitch/accel_z_g enjekte ederek doğrular."""
from __future__ import annotations
import time

import pytest

from mission import Mission
from sim_backend import FakeDrone


def _mission_with_drone():
    drone = FakeDrone()
    drone.connect()
    m = Mission(drone=drone)
    m.dropper = None
    m.setup()
    return m, drone


@pytest.mark.timeout(30)
def test_sustained_tilt_beyond_45deg_triggers_crash_disarm():
    """45° eşiğinin üzerinde sürdürülen tilt (yaw spin-up sırasında olabilecek
    aşırı roll/pitch) force-disarm + CRASH abort tetiklemeli."""
    m, drone = _mission_with_drone()
    try:
        drone.armed = True
        drone.roll_deg = 52.0   # 45° eşiğinin üzerinde
        deadline = time.time() + 5.0
        while time.time() < deadline and not m._abort:
            time.sleep(0.1)
        assert m._abort, "sürdürülen >45° tilt CRASH failsafe tetiklemeli"
        assert "CRASH" in m._abort_reason
        assert not drone.armed, "crash tespitinde force_disarm uygulanmalı"
    finally:
        m.close()
        drone.close()


@pytest.mark.timeout(30)
def test_transient_tilt_below_threshold_count_does_not_trigger():
    """Tek seferlik/kısa süreli 50° tilt (örn. rüzgar gust'ı geçici tepki)
    3 ardışık örnek şartını sağlamazsa YANLIŞ ALARM vermemeli — monitor 5 Hz
    (0.2s uyku) çalıştığından <0.3s'lik bir spike'ın tetiklememesi beklenir."""
    m, drone = _mission_with_drone()
    try:
        drone.armed = True
        drone.roll_deg = 50.0
        time.sleep(0.15)   # 3 örneklik pencereden (>=0.6s) çok kısa
        drone.roll_deg = 0.0
        time.sleep(1.0)
        assert not m._abort, "geçici/kısa tilt yanlış CRASH alarmı vermemeli"
    finally:
        m.close()
        drone.close()


@pytest.mark.timeout(30)
def test_accel_spike_beyond_3g_triggers_crash_disarm():
    """3g üzerinde sürdürülen ivme sıçraması (RAW_IMU accel_z_g) da devrilme/
    çarpma göstergesi sayılır ve CRASH failsafe'i tetiklemeli (tilt'ten
    bağımsız ikinci bir tetikleyici — mission.py crash monitor 'veya' mantığı)."""
    m, drone = _mission_with_drone()
    try:
        drone.armed = True
        drone.accel_z_g = 3.5   # 3g eşiğinin üzerinde
        deadline = time.time() + 5.0
        while time.time() < deadline and not m._abort:
            time.sleep(0.1)
        assert m._abort
        assert "CRASH" in m._abort_reason
        assert not drone.armed
    finally:
        m.close()
        drone.close()


@pytest.mark.timeout(30)
def test_yaw_spin_alone_without_tilt_does_not_trigger_crash():
    """Salt yaw dönüşü (heading spin-up), roll/pitch/accel_z_g normal kaldığı
    sürece CRASH tetiklememeli — crash detection sadece tilt/ivme bakar,
    yaw'ı izlemez (bilinen tasarım sınırı, bkz. final rapor)."""
    m, drone = _mission_with_drone()
    try:
        drone.armed = True
        for h in range(0, 720, 30):
            drone.heading = h % 360
            time.sleep(0.05)
        assert not m._abort
    finally:
        m.close()
        drone.close()
