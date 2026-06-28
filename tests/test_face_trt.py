"""M1 — TensorRT backend smoke + graceful fallback testleri."""
from __future__ import annotations
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "onboard"))

import face_verifier as fv  # noqa: E402


def test_find_engines_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KOKPIT_TRT_DIR", str(tmp_path / "nope"))
    det, emb = fv._find_engines()
    assert det is None and emb is None


def test_find_engines_picks_latest(tmp_path, monkeypatch):
    (tmp_path / "det_a.engine").write_bytes(b"x")
    (tmp_path / "det_b.engine").write_bytes(b"x")
    (tmp_path / "emb_x.engine").write_bytes(b"x")
    monkeypatch.setenv("KOKPIT_TRT_DIR", str(tmp_path))
    det, emb = fv._find_engines()
    assert det.endswith("det_b.engine")
    assert emb.endswith("emb_x.engine")


def test_trt_backend_load_no_engine(tmp_path):
    from config import CFG
    be = fv.TRTBackend(CFG.face, det_path=None, emb_path=None)
    assert be.load() is False


def test_verifier_trt_force_falls_back(monkeypatch):
    """force_backend=trt + engine yok → dlib/opencv fallback, çökmemeli."""
    monkeypatch.setenv("KOKPIT_TRT_DIR", "/tmp/nonexistent_trt_dir_kokpit")
    v = fv.FaceVerifier(force_backend="trt")
    assert v.backend_name in ("face_recognition", "opencv-fallback")


def test_arcface_ref_kps_shape():
    assert fv.ARCFACE_REF_KPS.shape == (5, 2)
    assert fv.ARCFACE_REF_KPS.dtype == np.float32


@pytest.mark.skipif(not fv._HAS_TRT, reason="tensorrt not installed")
def test_trt_engine_load_smoke():
    """Eğer Jetson'da engine varsa load smoke test."""
    det, emb = fv._find_engines()
    if not (det and emb):
        pytest.skip("no engines built")
    from config import CFG
    be = fv.TRTBackend(CFG.face, det, emb)
    assert be.load() is True
