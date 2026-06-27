"""ArUco tespiti ve config doğrulama testleri."""
import numpy as np
import cv2
import pytest

from aruco_detector import ArucoDetector
from config import Config, CFG


def _scene_with_marker(cx_off, cy_off, size=240):
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
    if hasattr(cv2.aruco, "generateImageMarker"):
        m = cv2.aruco.generateImageMarker(d, 0, size)
    else:
        m = cv2.aruco.drawMarker(d, 0, size)
    b = 40
    canvas = np.full((size + 2 * b, size + 2 * b), 255, np.uint8)
    canvas[b:b + size, b:b + size] = m
    canvas = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    scene = np.full((720, 1280, 3), 200, np.uint8)
    h, w = canvas.shape[:2]
    x0 = 640 - w // 2 + cx_off
    y0 = 360 - h // 2 + cy_off
    scene[y0:y0 + h, x0:x0 + w] = canvas
    return scene


def test_detect_centered_marker():
    det = ArucoDetector().detect(_scene_with_marker(0, 0))
    assert det.found and det.marker_id == 0
    assert abs(det.offset_norm_x) < 0.05
    assert abs(det.offset_norm_y) < 0.05


def test_offset_signs():
    # sağa kaydır -> +x, aşağı kaydır -> +y
    det = ArucoDetector().detect(_scene_with_marker(200, 120))
    assert det.found
    assert det.offset_norm_x > 0
    assert det.offset_norm_y > 0


def test_no_marker():
    blank = np.full((720, 1280, 3), 127, np.uint8)
    assert not ArucoDetector().detect(blank).found


def test_pose_distance_positive():
    det = ArucoDetector().detect(_scene_with_marker(0, 0))
    assert det.distance_m > 0


def test_config_valid_default():
    assert CFG.validate() == []


def test_config_catches_bad_drop_altitude():
    c = Config()
    c.flight.drop_altitude_m = 10.0  # 2-3 m hedefi dışında
    errs = c.validate()
    assert any("drop_altitude" in e for e in errs)


def test_config_catches_dropper_pwm_equal():
    c = Config()
    c.dropper.pwm_locked = c.dropper.pwm_released
    assert any("dropper" in e for e in c.validate())
