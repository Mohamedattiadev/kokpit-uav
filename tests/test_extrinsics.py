"""M2 — extrinsics transform testleri."""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

from extrinsics import (Extrinsics, MountOffset, _parse_simple_yaml,  # noqa: E402
                        load_extrinsics, transform_cam_to_body,
                        transform_lidar_to_body)


def test_identity_extrinsics_passthrough():
    ext = Extrinsics()
    v = np.array([1.0, 2.0, 3.0])
    out = transform_cam_to_body(v, ext)
    assert np.allclose(out, v)


def test_offset_extrinsics_adds_mount():
    ext = Extrinsics(cam_to_body=MountOffset(x=0.1, y=-0.05, z=0.2))
    out = transform_cam_to_body([0.0, 0.0, 0.0], ext)
    assert np.allclose(out, [0.1, -0.05, 0.2])


def test_lidar_offset():
    ext = Extrinsics(lidar_to_body=MountOffset(z=0.07))
    assert abs(transform_lidar_to_body(1.0, ext) - 1.07) < 1e-9


def test_simple_yaml_parser():
    txt = """
cam_to_body:
  x: 0.1
  y: 0.0
  z: 0.2  # comment
lidar_to_body:
  z: 0.05
"""
    d = _parse_simple_yaml(txt)
    assert d["cam_to_body"]["x"] == 0.1
    assert d["cam_to_body"]["z"] == 0.2
    assert d["lidar_to_body"]["z"] == 0.05


def test_load_default_yaml_exists():
    ext = load_extrinsics()
    # default dosya var → bir şeyler okumuş olmalı
    assert isinstance(ext, Extrinsics)
    assert isinstance(ext.cam_to_body, MountOffset)


def test_yaw_rotation_swaps_axes():
    ext = Extrinsics(cam_to_body=MountOffset(yaw=90.0))
    out = transform_cam_to_body([1.0, 0.0, 0.0], ext)
    # 90° yaw: x → y
    assert abs(out[0]) < 1e-9
    assert abs(out[1] - 1.0) < 1e-9
