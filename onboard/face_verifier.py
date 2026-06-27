"""
face_verifier.py — Biyometrik (yüz) kimlik doğrulama

Görev: Hedefte, İHA kameradan gördüğü kişinin yer istasyonunca gönderilen
yetkili alıcı (recipient_id) ile aynı kişi olduğunu doğrular. Eşleşme barajı
aşılırsa paket bırakılabilir; aşılamazsa teslimat ASKIYA alınır (rapor 2.1.4).

Veri seti: faces/alici_<id>.jpg  (her yetkili alıcı için bir referans foto).

Backend mimarisi:
  * FaceRecognitionBackend : üretim. `face_recognition` (dlib) — 128B embedding,
    öklid mesafesi ile eşleştirme. Jetson'da `model="hog"` (CPU) veya "cnn" (GPU).
  * OpenCVBackend          : `face_recognition` yoksa devreye giren hafif yedek
    (Haar yüz tespiti + histogram/ORB benzerliği). SADECE test/geliştirme içindir;
    üretimde face_recognition kurulu olmalıdır.

Karar: çoklu kare oylaması (votes_required kareden votes_needed_to_pass eşleşme).
"""
from __future__ import annotations
import os
import glob
import time
from dataclasses import dataclass

import numpy as np
import cv2

from config import CFG, FaceConfig

# --- Backend seçimi ---
try:
    import face_recognition          # noqa
    _HAS_FR = True
except Exception:
    _HAS_FR = False


@dataclass
class VerifyResult:
    matched: bool = False
    confidence: float = 0.0     # 0..1 (1 = mükemmel)
    distance: float = 1.0       # backend mesafesi (küçük = iyi)
    face_found: bool = False
    recipient_id: int = -1


# ---------------------------------------------------------------- backend'ler
class FaceRecognitionBackend:
    """Üretim backend'i (dlib tabanlı face_recognition)."""
    def __init__(self, cfg: FaceConfig):
        self.cfg = cfg
        self.encodings: dict[int, np.ndarray] = {}

    def enroll(self, recipient_id: int, image_bgr):
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        locs = face_recognition.face_locations(rgb, model=self.cfg.model)
        if not locs:
            return False
        encs = face_recognition.face_encodings(rgb, locs)
        if not encs:
            return False
        self.encodings[recipient_id] = encs[0]
        return True

    def verify(self, recipient_id: int, frame_bgr) -> VerifyResult:
        res = VerifyResult(recipient_id=recipient_id)
        if recipient_id not in self.encodings:
            return res
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        locs = face_recognition.face_locations(rgb, model=self.cfg.model)
        if not locs:
            return res
        res.face_found = True
        encs = face_recognition.face_encodings(rgb, locs)
        ref = self.encodings[recipient_id]
        dists = face_recognition.face_distance(encs, ref)
        d = float(np.min(dists))
        res.distance = d
        # mesafeyi 0..1 güvene çevir (eşik=match_distance_threshold)
        res.confidence = max(0.0, 1.0 - d / 0.6)
        res.matched = d <= self.cfg.match_distance_threshold
        return res


class OpenCVBackend:
    """Hafif yedek backend (face_recognition yoksa). SADECE test içindir.

    Haar ile yüz bul, gri 100x100 normalize et, referansla histogram korelasyonu
    + şablon benzerliği hesapla. Embedding kadar güvenilir DEĞİLDİR."""
    def __init__(self, cfg: FaceConfig):
        self.cfg = cfg
        self.refs: dict[int, np.ndarray] = {}
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.detector = cv2.CascadeClassifier(cascade_path)

    def _largest_face(self, image_bgr):
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.detector.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
        if len(faces) == 0:
            # Yüz tespit edilemezse tüm kareyi kullan (test kolaylığı)
            return cv2.resize(gray, (100, 100))
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        return cv2.resize(gray[y:y + h, x:x + w], (100, 100))

    def enroll(self, recipient_id: int, image_bgr):
        self.refs[recipient_id] = cv2.equalizeHist(self._largest_face(image_bgr))
        return True

    def verify(self, recipient_id: int, frame_bgr) -> VerifyResult:
        res = VerifyResult(recipient_id=recipient_id)
        if recipient_id not in self.refs:
            return res
        face = cv2.equalizeHist(self._largest_face(frame_bgr))
        res.face_found = True
        ref = self.refs[recipient_id]
        # Normalize korelasyon (template matching)
        score = float(cv2.matchTemplate(face, ref, cv2.TM_CCOEFF_NORMED).max())
        res.confidence = max(0.0, score)
        res.distance = 1.0 - score
        res.matched = score >= 0.5   # yedek için gevşek eşik
        return res


# ---------------------------------------------------------------- ön yüz
class FaceVerifier:
    def __init__(self, cfg: FaceConfig | None = None, force_backend: str | None = None):
        self.cfg = cfg or CFG.face
        if force_backend == "opencv" or (not _HAS_FR and force_backend != "fr"):
            self.backend = OpenCVBackend(self.cfg)
            self.backend_name = "opencv-fallback"
            if not _HAS_FR:
                print("[YÜZ] UYARI: face_recognition yok -> OpenCV yedek backend "
                      "(üretimde 'pip install face_recognition' kur!)")
        else:
            self.backend = FaceRecognitionBackend(self.cfg)
            self.backend_name = "face_recognition"
        self.enrolled: list[int] = []

    def load_dataset(self, directory: str | None = None) -> int:
        """faces/alici_<id>.jpg dosyalarını yükle. Yüklenen sayısını döndür."""
        directory = directory or self.cfg.dataset_dir
        count = 0
        for path in glob.glob(os.path.join(directory, "alici_*.*")):
            base = os.path.splitext(os.path.basename(path))[0]
            try:
                rid = int(base.split("_")[1])
            except (IndexError, ValueError):
                continue
            img = cv2.imread(path)
            if img is None:
                continue
            if self.backend.enroll(rid, img):
                self.enrolled.append(rid)
                count += 1
                print(f"[YÜZ] Kayıt: alıcı {rid} <- {os.path.basename(path)}")
            else:
                print(f"[YÜZ] UYARI: {path} içinde yüz bulunamadı")
        print(f"[YÜZ] Toplam {count} alıcı kaydedildi (backend={self.backend_name})")
        return count

    def verify_frame(self, recipient_id: int, frame) -> VerifyResult:
        return self.backend.verify(recipient_id, frame)

    def verify_with_voting(self, recipient_id: int, camera,
                           on_frame=None) -> VerifyResult:
        """Birden çok kare topla, oyla. votes_needed_to_pass eşleşme -> PASS."""
        votes = 0
        checked = 0
        best = VerifyResult(recipient_id=recipient_id)
        start = time.time()
        while (checked < self.cfg.votes_required and
               time.time() - start < self.cfg.verify_timeout_s):
            ok, frame = camera.read()
            if not ok or frame is None:
                continue
            r = self.verify_frame(recipient_id, frame)
            if on_frame:
                on_frame(frame, r)
            if r.face_found:
                checked += 1
                if r.confidence > best.confidence:
                    best = r
                if r.matched:
                    votes += 1
            time.sleep(0.05)
        best.matched = votes >= self.cfg.votes_needed_to_pass
        print(f"[YÜZ] Oylama: {votes}/{checked} eşleşme "
              f"(gerekli {self.cfg.votes_needed_to_pass}) -> "
              f"{'PASS' if best.matched else 'FAIL'}")
        return best
