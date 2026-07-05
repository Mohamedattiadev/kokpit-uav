"""Biyometrik doğrulama — gerçek dünya kenar durumları.

Literatürden (NIST FRVT, düşük ışık/motion-blur/pose çalışmaları — bkz. rapor):
  * Maskeleme/okluzyon: doğru eşleşen algoritmalarda bile hata oranı ~16x artar.
  * Düşük ışık + motion blur: enroll/verify başarısızlığının başlıca nedeni.
  * Yanlış kişi (impostor) reddi: FAR düşük tutulmalı (rapor: %90 eşik).

Bu testler face_verifier.py'nin oy tabanlı karar mantığını (votes_required/
votes_needed_to_pass) ve %90 eşik sınırındaki davranışını, gerçek OpenCV
backend'i üzerinden senaryo bazlı doğrular (TensorRT/dlib ağırlık dosyası
gerektirmez — CI'da çalışabilir)."""
from __future__ import annotations
import time

import numpy as np
import cv2
import pytest

from face_verifier import FaceVerifier, VerifyResult
from config import CFG


class _FrameFeedCamera:
    """Sabit bir kare listesini sırayla (biterse tekrar) döndüren sahte kamera."""
    def __init__(self, frames, fail_every: int = 0):
        self.frames = frames
        self.i = 0
        self.fail_every = fail_every   # >0 ise N karede bir "kamera hatası" simüle et

    def read(self):
        self.i += 1
        if self.fail_every and self.i % self.fail_every == 0:
            return False, None
        return True, self.frames[self.i % len(self.frames)]


class _NoFaceCamera:
    """Hiçbir zaman geçerli kare vermeyen kamera (no-face-found / donanım kesintisi)."""
    def read(self):
        return False, None


def _solid_frame(gray_level=128):
    return np.full((120, 120, 3), gray_level, dtype=np.uint8)


def _textured_frame(seed=0):
    """matchTemplate (TM_CCOEFF_NORMED) sıfır varyanslı düz karede tanımsız
    davranır — gerçekçi biyometrik karşılaştırma için dokulu (rastgele ama
    deterministik) bir 'yüz benzeri' kare üretir."""
    rng = np.random.RandomState(seed)
    img = rng.randint(60, 200, size=(120, 120), dtype=np.uint8)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_no_face_found_times_out_without_busy_loop():
    """Kamera hiç kare vermezse verify_with_voting, verify_timeout_s içinde
    döner (sonsuz/aşırı sık CPU spin yapmaz — bkz. onboard/face_verifier.py
    verify_with_voting busy-wait düzeltmesi) ve matched=False verir."""
    v = FaceVerifier(force_backend="opencv")
    v.cfg.verify_timeout_s = 0.4
    v.enrolled = [7]
    cam = _NoFaceCamera()
    t0 = time.time()
    calls = {"n": 0}
    real_read = cam.read

    def counted_read():
        calls["n"] += 1
        return real_read()
    cam.read = counted_read
    r = v.verify_with_voting(7, cam)
    elapsed = time.time() - t0
    assert not r.matched
    assert elapsed < 1.0, "timeout süresini aşırı aşmamalı"
    # 0.4s / 0.05s uyku ~= 8 civarı çağrı beklenir; busy-loop olsaydı binlerce olurdu.
    assert calls["n"] < 100, "busy-wait regresyonu: kamera hata döngüsü CPU'yu boşa yakıyor"


def test_wrong_person_rejected_not_enrolled():
    """Kayıtlı olmayan recipient_id için verify daima face_found=False döner
    (impostor / kayıt dışı kişi -> reddedilir, güvenlik varsayılanı)."""
    v = FaceVerifier(force_backend="opencv")
    r = v.verify_frame(999, _solid_frame())
    assert not r.matched
    assert not r.face_found


def test_confidence_threshold_boundary_votes():
    """votes_needed_to_pass eşiğinin altı/üstü doğru PASS/FAIL kararı vermeli.

    OpenCV yedek backend'i template-matching tabanlı olduğundan gerçekçi bir
    "confidence" üretmesi için referans ile aynı kareyi kullanıyoruz (mükemmel
    eşleşme) ve enrolled olmayan farklı bir kare ile karışık besleyerek oy
    sayısını eşik sınırının hemen altına/üstüne düşürüyoruz."""
    v = FaceVerifier(force_backend="opencv")
    ref = _textured_frame(seed=1)
    other = _textured_frame(seed=2)
    v.backend.enroll(7, ref)
    v.cfg.votes_required = 5
    v.cfg.votes_needed_to_pass = 3
    v.cfg.verify_timeout_s = 5.0

    # 3/5 eşleşme (referansla aynı doku) -> PASS beklenir (>= eşik)
    frames_pass = [ref, ref, ref, other, other]
    r_pass = v.verify_with_voting(7, _FrameFeedCamera(frames_pass))
    assert r_pass.matched, "3/5 oy eşik(3)'i karşılamalı -> PASS"

    # 2/5 eşleşme (eşik 3'ün altında) -> FAIL beklenir
    v2 = FaceVerifier(force_backend="opencv")
    v2.backend.enroll(7, ref)
    v2.cfg.votes_required = 5
    v2.cfg.votes_needed_to_pass = 3
    v2.cfg.verify_timeout_s = 5.0
    frames_fail = [ref, ref, other, other, other]
    r_fail = v2.verify_with_voting(7, _FrameFeedCamera(frames_fail))
    assert not r_fail.matched, "2/5 oy eşik(3)'in altında -> FAIL"


def test_low_light_degrades_confidence_but_still_bounded():
    """Aşırı düşük ışık (neredeyse siyah kare) confidence'ı düşürür ama
    crash/exception olmadan bounded [0,1] bir sonuç üretmeli."""
    v = FaceVerifier(force_backend="opencv")
    v.backend.enroll(7, _solid_frame(128))
    dark = _solid_frame(2)   # aşırı düşük ışık
    r = v.verify_frame(7, dark)
    assert 0.0 <= r.confidence <= 1.0
    assert 0.0 <= r.distance <= 1.0


@pytest.mark.parametrize("distance,expect_match", [
    (0.44, True),    # eşik(0.45) altı -> eşleş
    (0.46, False),   # eşik üstü -> reddet
])
def test_face_recognition_backend_threshold_boundary(monkeypatch, distance, expect_match):
    """FaceRecognitionBackend.verify sınır değerlerinde doğru karar vermeli
    (rapor: %90 eşleşme hedefi -> match_distance_threshold=0.45)."""
    fr = pytest.importorskip("face_recognition")
    from face_verifier import FaceRecognitionBackend

    be = FaceRecognitionBackend(CFG.face)
    fake_encoding = np.zeros(128, dtype=np.float64)
    be.encodings[7] = fake_encoding

    monkeypatch.setattr(fr, "face_locations", lambda rgb, model=None: [(0, 10, 10, 0)])
    monkeypatch.setattr(fr, "face_encodings", lambda rgb, locs: [fake_encoding])
    monkeypatch.setattr(fr, "face_distance", lambda encs, ref: np.array([distance]))

    r = be.verify(7, _solid_frame())
    assert r.matched is expect_match
    assert r.distance == pytest.approx(distance)
