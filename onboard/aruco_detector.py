"""
aruco_detector.py — ArUco marker tespiti ve poz kestirimi (OpenCV)

Yer ünitesi (ped) üzerindeki ArUco marker'ı bulur, görüntü merkezine göre
yatay kaymayı (offset) ve metre cinsinden 3B pozu hesaplar. Bu çıktı,
visual_servo PID döngüsünü besler (rapor 3.1.5 / 3.3.1.3 "Visual Servoing").

Koordinat tanımı (alta bakan kamera, image-up = İHA ileri/Kuzey kabulü):
    offset_fwd  : +ileri (Kuzey) yönünde hata  (marker merkezin üstündeyse +)
    offset_right: +sağ (Doğu) yönünde hata      (marker merkezin sağındaysa +)
    distance_m  : marker'a metre uzaklık (poz tahmininden, ~irtifa)
Mounting/işaret farkları config + visual_servo tarafında ayarlanır.

OpenCV 4.7+ yeni ArUco API (ArucoDetector) ve eski API (detectMarkers) ikisi
de desteklenir.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import cv2

from config import CFG, ArucoConfig
from camera import load_intrinsics
from extrinsics import load_extrinsics, transform_cam_to_body


def _get_dictionary(name: str):
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


@dataclass
class Detection:
    found: bool = False
    marker_id: int = -1
    center_px: tuple = (0.0, 0.0)
    # Görüntü merkezine göre normalize kayma (-1..1)
    offset_norm_x: float = 0.0   # +sağ
    offset_norm_y: float = 0.0   # +aşağı (image)
    # Kontrol için gövde hataları (metre, poz tahmininden)
    offset_fwd_m: float = 0.0    # +Kuzey/ileri
    offset_right_m: float = 0.0  # +Doğu/sağ
    distance_m: float = 0.0      # marker'a uzaklık (~irtifa)
    yaw_deg: float = 0.0
    corners: object = None


class ArucoDetector:
    def __init__(self, cfg: ArucoConfig | None = None):
        self.cfg = cfg or CFG.aruco
        self.dictionary = _get_dictionary(self.cfg.dictionary)
        # Yeni/eski API uyumu
        if hasattr(cv2.aruco, "ArucoDetector"):
            params = cv2.aruco.DetectorParameters()
            self._detector = cv2.aruco.ArucoDetector(self.dictionary, params)
            self._new_api = True
        else:
            self._params = cv2.aruco.DetectorParameters_create()
            self._new_api = False
        self.cam_mtx, self.dist = load_intrinsics(CFG.camera)
        self.marker_len = self.cfg.marker_length_m
        self.extrinsics = load_extrinsics()

    def _detect_raw(self, gray):
        if self._new_api:
            corners, ids, _ = self._detector.detectMarkers(gray)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(
                gray, self.dictionary, parameters=self._params)
        return corners, ids

    def detect(self, frame) -> Detection:
        if frame is None:
            return Detection(found=False)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        h, w = gray.shape[:2]
        corners, ids = self._detect_raw(gray)
        if ids is None or len(ids) == 0:
            return Detection(found=False)

        # Hedef ID'yi seç (yoksa ilk marker)
        ids_flat = ids.flatten().tolist()
        if self.cfg.target_id in ids_flat:
            idx = ids_flat.index(self.cfg.target_id)
        else:
            idx = 0
        marker_corners = corners[idx]
        marker_id = int(ids_flat[idx])

        # Merkez piksel
        c = marker_corners.reshape((4, 2))
        cx_px = float(c[:, 0].mean())
        cy_px = float(c[:, 1].mean())
        off_nx = (cx_px - w / 2.0) / (w / 2.0)
        off_ny = (cy_px - h / 2.0) / (h / 2.0)

        det = Detection(
            found=True, marker_id=marker_id, center_px=(cx_px, cy_px),
            offset_norm_x=off_nx, offset_norm_y=off_ny, corners=marker_corners)

        # Metrik poz kestirimi
        try:
            rvec, tvec = self._estimate_pose(marker_corners)
            # Kamera çerçevesi → gövde uyumlu vektör (offset_fwd = -tvec_y,
            # offset_right = tvec_x, distance = tvec_z) sonra mount extrinsics.
            body_in = np.array([float(-tvec[1]), float(tvec[0]),
                                float(tvec[2])])  # (fwd, right, down/dist)
            body = transform_cam_to_body(body_in, self.extrinsics)
            det.offset_fwd_m = float(body[0])
            det.offset_right_m = float(body[1])
            det.distance_m = float(body[2])
            rot, _ = cv2.Rodrigues(rvec)
            det.yaw_deg = float(np.degrees(np.arctan2(rot[1, 0], rot[0, 0])))
        except Exception:
            # Poz çıkmazsa normalize pikselden kaba metre tahmini (irtifa bilinirse
            # visual_servo daha iyi ölçekler). Burada 0 bırakıyoruz.
            pass
        return det

    def _estimate_pose(self, marker_corners):
        half = self.marker_len / 2.0
        obj = np.array([[-half, half, 0], [half, half, 0],
                        [half, -half, 0], [-half, -half, 0]], dtype=np.float32)
        img_pts = marker_corners.reshape((4, 2)).astype(np.float32)
        ok, rvec, tvec = cv2.solvePnP(
            obj, img_pts, self.cam_mtx, self.dist,
            flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not ok:
            raise RuntimeError("solvePnP başarısız")
        return rvec.flatten(), tvec.flatten()

    def draw(self, frame, det: Detection):
        """Görselleştirme (debug/log)."""
        if det.found and det.corners is not None:
            cv2.aruco.drawDetectedMarkers(frame, [det.corners],
                                          np.array([[det.marker_id]]))
            cx, cy = int(det.center_px[0]), int(det.center_px[1])
            cv2.circle(frame, (cx, cy), 6, (0, 255, 0), -1)
            cv2.putText(frame, f"d={det.distance_m:.2f}m", (cx + 8, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        return frame
