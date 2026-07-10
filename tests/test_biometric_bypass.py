"""Madde 4 — biyometrik doğrulama yarışma günü bypass'ı.

Varsayılan FaceConfig (verification_bypassed=False) davranışı DEĞİŞMEMELİ
(mevcut face_verifier testleri buna dayanıyor). Mission ise KENDİ
verifier'ını bypass'lı kurar.
"""
from __future__ import annotations
from dataclasses import replace
from unittest.mock import MagicMock

from config import CFG
from face_verifier import FaceVerifier, VerifyResult
from mission import Mission


class _OneFrameCam:
    def read(self):
        import numpy as np
        return True, np.zeros((10, 10, 3), dtype="uint8")


def test_default_faceconfig_not_bypassed():
    assert CFG.face.verification_bypassed is False


def test_bypassed_verifier_always_matches():
    cfg = replace(CFG.face, verification_bypassed=True)
    v = FaceVerifier(cfg=cfg, force_backend="opencv")
    res = v.verify_with_voting(recipient_id=999, camera=_OneFrameCam())
    assert isinstance(res, VerifyResult)
    assert res.matched is True
    assert res.face_found is True


def test_non_bypassed_verifier_unaffected_by_unknown_recipient():
    v = FaceVerifier(force_backend="opencv")
    res = v.verify_with_voting(recipient_id=999, camera=_OneFrameCam())
    assert res.matched is False, "kayıt yoksa normal mantık PASS vermemeli"


def test_mission_default_verifier_is_bypassed():
    drone = MagicMock()
    m = Mission(drone=drone, lora=MagicMock())
    assert m.verifier.cfg.verification_bypassed is True
    res = m.verifier.verify_with_voting(recipient_id=0, camera=_OneFrameCam())
    assert res.matched is True
