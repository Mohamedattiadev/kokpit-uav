"""Face verifier edge testleri."""
from __future__ import annotations
import numpy as np
import pytest

from face_verifier import FaceVerifier


def test_enroll_from_jpeg_invalid_bytes():
    """Bozuk JPEG → enroll_from_jpeg False, crash yok."""
    v = FaceVerifier(force_backend="opencv")
    ok = v.enroll_from_jpeg(b"\xff\xff\xff", recipient_id=99)
    assert ok is False


def test_enroll_from_jpeg_empty():
    v = FaceVerifier(force_backend="opencv")
    assert v.enroll_from_jpeg(b"", recipient_id=99) is False


def test_enroll_from_jpeg_valid_image_succeeds():
    """Geçerli JPEG (yüz olmasa bile) OpenCV fallback backend kabul eder.
    Üretimde face_recognition backend yüzü gerçekten tespit etmek için
    kullanılır; bu test sadece decode + enroll yolunun crash etmediğini
    doğrular."""
    import cv2
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    ok_encode, buf = cv2.imencode(".jpg", img)
    assert ok_encode
    v = FaceVerifier(force_backend="opencv")
    ok = v.enroll_from_jpeg(bytes(buf), recipient_id=99)
    # OpenCV backend fallback: yüz yoksa tüm kareyi enroll eder → True
    assert ok is True
    assert 99 in v.enrolled


def test_verifier_load_dataset_missing_dir():
    """Var olmayan dataset dir → 0 enroll, crash yok."""
    v = FaceVerifier(force_backend="opencv")
    n = v.load_dataset(directory="/tmp/nonexistent_kokpit_faces_xyz")
    assert n == 0
