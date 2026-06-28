"""
extrinsics.py — Kamera/lidar mount offset → gövde çerçevesi dönüşümü.

Rapor: hassas iniş ±14 cm hedefler; kamera/lidar gövde merkezinden uzaktaysa
naif tvec doğrudan komut beslerse 5-10 cm sessiz hata oluşur. Bu modül:
  - configs/extrinsics.yaml okur (basit alt-küme parser; pyyaml opsiyonel)
  - transform_cam_to_body(tvec_cam, R_cam_body=None) → tvec_body
  - transform_lidar_to_body(z_lidar) → z_body (gövde altı zemin uzaklığı)
"""
from __future__ import annotations
import math
import os
from dataclasses import dataclass, field

import numpy as np

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "configs",
                            "extrinsics.yaml")


@dataclass
class MountOffset:
    x: float = 0.0   # ileri (gövde)
    y: float = 0.0   # sağ
    z: float = 0.0   # aşağı
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


@dataclass
class Extrinsics:
    cam_to_body: MountOffset = field(default_factory=MountOffset)
    lidar_to_body: MountOffset = field(default_factory=MountOffset)


def _parse_simple_yaml(text: str) -> dict:
    """Düz key/value + tek seviye dict yaml subset parser. pyyaml gerektirmez."""
    out: dict = {}
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if stripped.endswith(":") and indent == 0:
            key = stripped[:-1].strip()
            current = {}
            out[key] = current
            continue
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            v = v.split("#", 1)[0].strip()
            try:
                val: float | str = float(v)
            except ValueError:
                val = v
            if indent == 0:
                out[k.strip()] = val
            elif current is not None:
                current[k.strip()] = val
    return out


def load_extrinsics(path: str | None = None) -> Extrinsics:
    """YAML dosyasından extrinsics yükle. Eksikse default (identity)."""
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        return Extrinsics()
    try:
        try:
            import yaml  # type: ignore
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            with open(path) as f:
                data = _parse_simple_yaml(f.read())
    except OSError:
        return Extrinsics()
    cam = data.get("cam_to_body", {}) or {}
    lid = data.get("lidar_to_body", {}) or {}
    return Extrinsics(
        cam_to_body=MountOffset(**{k: float(cam.get(k, 0.0))
                                   for k in ("x", "y", "z",
                                             "roll", "pitch", "yaw")}),
        lidar_to_body=MountOffset(**{k: float(lid.get(k, 0.0))
                                     for k in ("x", "y", "z",
                                               "roll", "pitch", "yaw")}),
    )


def _rotation_matrix(roll_deg: float, pitch_deg: float, yaw_deg: float):
    r, p, y = (math.radians(a) for a in (roll_deg, pitch_deg, yaw_deg))
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def transform_cam_to_body(tvec_cam, ext: Extrinsics | None = None,
                          cam_axis_to_body: np.ndarray | None = None):
    """tvec_cam (kamera çerçevesi, x=sağ y=aşağı z=ileri) → gövde tvec.

    Önce kamera→gövde aks dönüşümü (alta bakan kamera için varsayılan eşleme:
    cam_x→body_y, cam_y→body_x, cam_z→body_z) sonra mount offset ekle.
    """
    ext = ext or load_extrinsics()
    tvec = np.asarray(tvec_cam, dtype=np.float64).reshape(3)
    if cam_axis_to_body is None:
        # Alta bakan kamera default eşleme:
        #   cam x (sağ)   → body y (sağ)
        #   cam y (aşağı) → body x (ileri)? Hayır — image-y aşağı = gövde -x DEĞIL.
        # Aruco_detector zaten "offset_fwd = -y, offset_right = x" yapıyor.
        # Burada kameranın ölçtüğü gövde-uyumlu vektörü kabul ediyoruz; sadece
        # mount rotation + translation uygulayacağız.
        cam_axis_to_body = np.eye(3)
    R_mount = _rotation_matrix(ext.cam_to_body.roll,
                               ext.cam_to_body.pitch,
                               ext.cam_to_body.yaw)
    body = R_mount @ (cam_axis_to_body @ tvec)
    body[0] += ext.cam_to_body.x
    body[1] += ext.cam_to_body.y
    body[2] += ext.cam_to_body.z
    return body


def transform_lidar_to_body(z_lidar: float,
                            ext: Extrinsics | None = None) -> float:
    """Lidar mesafe → gövde altı zemin uzaklığı.

    Lidar gövde merkezinden lidar_to_body.z kadar aşağıda monte; ölçtüğü
    mesafeden bu offset'i ekleyerek/çıkararak gövde altı uzaklığı verir.
    Aşağı yönü pozitif kabul (NED z = aşağı +): gövde altı = z_lidar + z_offset.
    """
    ext = ext or load_extrinsics()
    return float(z_lidar) + float(ext.lidar_to_body.z)
