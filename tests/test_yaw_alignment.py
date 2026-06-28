"""M6 — yaw alignment + condition_yaw testleri."""
from __future__ import annotations
import math
import os
import sys
from unittest.mock import MagicMock

import numpy as np
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from visual_servo import marker_yaw_to_heading  # noqa: E402


def test_zero_yaw_returns_drone_heading():
    assert abs(marker_yaw_to_heading(0.0, 90.0) - 90.0) < 1e-9


def test_yaw_wraps_360():
    assert abs(marker_yaw_to_heading(45.0, 350.0) - 35.0) < 1e-9


def test_negative_marker_yaw():
    h = marker_yaw_to_heading(-30.0, 100.0)
    assert abs(h - 70.0) < 1e-9


def test_condition_yaw_command_invoked():
    """DroneController.condition_yaw → MAV_CMD_CONDITION_YAW command_long_send."""
    import mavlink_interface as mi
    dc = mi.DroneController.__new__(mi.DroneController)
    dc.master = MagicMock()
    dc.master.target_system = 1
    dc.master.target_component = 1
    dc.condition_yaw(180.0, relative=False)
    args = dc.master.mav.command_long_send.call_args[0]
    # arg[2] = command id, arg[4] = p1 = heading
    cmd_id = args[2]
    p1 = args[4]
    assert cmd_id == mi.mavutil.mavlink.MAV_CMD_CONDITION_YAW
    assert abs(p1 - 180.0) < 1e-9


def test_rvec_yaw_extract():
    """cv2.Rodrigues + atan2 — sanity check."""
    rvec = np.array([0.0, 0.0, math.radians(45)])
    R, _ = cv2.Rodrigues(rvec)
    yaw = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    assert abs(yaw - 45.0) < 1e-3
