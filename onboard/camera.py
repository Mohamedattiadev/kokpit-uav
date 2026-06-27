"""
camera.py — Alt kamera erişim katmanı (IMX219 / USB / test)

Üç kaynak desteklenir:
  * CSICamera  : Jetson Orin Nano + IMX219 (GStreamer/nvarguscamerasrc)
  * USBCamera  : USB webcam veya laptop kamerası (geliştirme/test)
  * ImageCamera: tek bir görüntüyü tekrar tekrar veren sahte kamera (birim test)

open_camera(cfg) ortam/SIMULATION durumuna göre doğru kaynağı seçer.
Kamera iç parametreleri (matris + distorsiyon) get_intrinsics() ile alınır;
varsa camera_calibration.npz dosyasından, yoksa config varsayılanlarından.
"""
from __future__ import annotations
import os
import numpy as np
import cv2

from config import CFG, CameraConfig


def load_intrinsics(cfg: CameraConfig):
    """(camera_matrix 3x3, dist_coeffs) döndürür."""
    if os.path.exists(cfg.calibration_file):
        data = np.load(cfg.calibration_file)
        return data["camera_matrix"], data["dist_coeffs"]
    cam_mtx = np.array([[cfg.fx, 0, cfg.cx],
                        [0, cfg.fy, cfg.cy],
                        [0, 0, 1]], dtype=np.float64)
    dist = np.array(cfg.dist_coeffs, dtype=np.float64)
    return cam_mtx, dist


class Camera:
    """Soyut kamera arayüzü."""
    def read(self):
        raise NotImplementedError

    def release(self):
        pass

    def get_intrinsics(self):
        return load_intrinsics(CFG.camera)


class CSICamera(Camera):
    def __init__(self, cfg: CameraConfig):
        self.cap = cv2.VideoCapture(cfg.gstreamer_pipeline(), cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            raise RuntimeError("CSI kamera açılamadı (GStreamer pipeline)")

    def read(self):
        return self.cap.read()

    def release(self):
        self.cap.release()


class USBCamera(Camera):
    def __init__(self, cfg: CameraConfig):
        self.cap = cv2.VideoCapture(cfg.device_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            raise RuntimeError(f"USB kamera açılamadı (index {cfg.device_index})")

    def read(self):
        return self.cap.read()

    def release(self):
        self.cap.release()


class ImageCamera(Camera):
    """Statik bir görüntüyü döndüren sahte kamera (birim test / demo)."""
    def __init__(self, image):
        if isinstance(image, str):
            image = cv2.imread(image)
        if image is None:
            raise ValueError("ImageCamera: görüntü yüklenemedi")
        self.image = image

    def read(self):
        return True, self.image.copy()


def open_camera(cfg: CameraConfig | None = None) -> Camera:
    cfg = cfg or CFG.camera
    if CFG.simulation:
        # SITL'de gerçek kamera yok; sentetik kamera SITL harness'inde verilir.
        # Burada güvenli varsayılan: USB index (varsa) — yoksa çağıran SimCamera koyar.
        try:
            return USBCamera(cfg)
        except Exception:
            raise RuntimeError(
                "SIMULATION modunda gerçek kamera yok. SITL testinde "
                "sitl.sim_camera.SimDownCamera kullanın.")
    if cfg.use_gstreamer:
        return CSICamera(cfg)
    return USBCamera(cfg)
