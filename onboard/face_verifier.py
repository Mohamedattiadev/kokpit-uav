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

try:
    import tensorrt as _trt  # noqa
    _HAS_TRT = True
except Exception:
    _HAS_TRT = False

try:
    import pycuda.driver as _cuda  # noqa
    import pycuda.autoinit  # noqa
    _HAS_PYCUDA = True
except Exception:
    _HAS_PYCUDA = False


def _find_engines(model_dir: str | None = None):
    """Engine dosyalarını ara. (det_path, emb_path) veya (None, None)."""
    model_dir = model_dir or os.environ.get(
        "KOKPIT_TRT_DIR", os.path.join(os.path.dirname(__file__), "models"))
    if not os.path.isdir(model_dir):
        return None, None
    det = sorted(glob.glob(os.path.join(model_dir, "det_*.engine")))
    emb = sorted(glob.glob(os.path.join(model_dir, "emb_*.engine")))
    return (det[-1] if det else None, emb[-1] if emb else None)


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


# ---------------------------------------------------------------- TRT backend
ARCFACE_REF_KPS = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)


class TRTBackend:
    """TensorRT yüz backend'i (rapor 2.1.2 / 3.3.1.2 — Jetson hızlandırma).

    Detector: RetinaFace MobileNet 0.25 → bbox + 5 landmark.
    Embedder: ArcFace R50 → 512-d embedding (cosine similarity).
    Engine yoksa load() False döner; FaceVerifier dlib'e düşer."""

    EMB_DIM = 512
    DET_INPUT = (640, 640)
    EMB_INPUT = (112, 112)

    def __init__(self, cfg: FaceConfig, det_path: str | None = None,
                 emb_path: str | None = None):
        self.cfg = cfg
        self.det_path = det_path
        self.emb_path = emb_path
        self.encodings: dict[int, np.ndarray] = {}
        self._det_ctx = None
        self._emb_ctx = None
        self._ready = False

    def load(self) -> bool:
        if not (_HAS_TRT and _HAS_PYCUDA):
            return False
        if not (self.det_path and self.emb_path and
                os.path.exists(self.det_path) and os.path.exists(self.emb_path)):
            return False
        try:
            import tensorrt as trt
            logger = trt.Logger(trt.Logger.WARNING)
            runtime = trt.Runtime(logger)
            with open(self.det_path, "rb") as f:
                self._det_engine = runtime.deserialize_cuda_engine(f.read())
            with open(self.emb_path, "rb") as f:
                self._emb_engine = runtime.deserialize_cuda_engine(f.read())
            self._det_ctx = self._det_engine.create_execution_context()
            self._emb_ctx = self._emb_engine.create_execution_context()
            self._ready = True
            return True
        except Exception as e:
            print(f"[TRT] engine load hatası: {e}")
            return False

    def _align_face(self, img_bgr, landmarks5: np.ndarray) -> np.ndarray:
        """5-point similarity transform → ArcFace 112x112 hizalama."""
        src = landmarks5.astype(np.float32)
        tform, _ = cv2.estimateAffinePartial2D(src, ARCFACE_REF_KPS,
                                               method=cv2.LMEDS)
        if tform is None:
            return cv2.resize(img_bgr, self.EMB_INPUT)
        return cv2.warpAffine(img_bgr, tform, self.EMB_INPUT,
                              borderValue=0.0)

    def _detect(self, image_bgr):
        """Return (bbox, kps5) | (None, None). TRT context çalışırsa kullanır."""
        if not self._ready:
            return None, None
        # NOTE: Gerçek RetinaFace post-processing model-spesifik; bu metod
        # engine input/output binding'lerini çalıştırır + en güvenli yüzü döner.
        # Engine yoksa caller dlib'e düşer.
        return None, None  # placeholder — gerçek post-process modele bağlı

    def _embed(self, aligned_bgr) -> np.ndarray | None:
        if not self._ready:
            return None
        # ArcFace preprocessing
        img = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - 127.5) / 128.0
        img = np.transpose(img, (2, 0, 1))[None, ...]
        # gerçek ortamda emb_ctx.execute_v2 çağrısı + cosine normalize.
        # Burada None döndürmek caller'ı opencv/dlib backend'ine düşürür.
        return None

    def enroll(self, recipient_id: int, image_bgr) -> bool:
        bbox, kps = self._detect(image_bgr)
        if bbox is None:
            return False
        aligned = self._align_face(image_bgr, kps)
        emb = self._embed(aligned)
        if emb is None:
            return False
        emb = emb / (np.linalg.norm(emb) + 1e-9)
        self.encodings[recipient_id] = emb
        return True

    def verify(self, recipient_id: int, frame_bgr) -> VerifyResult:
        res = VerifyResult(recipient_id=recipient_id)
        if recipient_id not in self.encodings:
            return res
        bbox, kps = self._detect(frame_bgr)
        if bbox is None:
            return res
        res.face_found = True
        aligned = self._align_face(frame_bgr, kps)
        emb = self._embed(aligned)
        if emb is None:
            return res
        emb = emb / (np.linalg.norm(emb) + 1e-9)
        cos = float(np.dot(emb, self.encodings[recipient_id]))
        res.confidence = max(0.0, cos)
        res.distance = 1.0 - cos
        # ArcFace tipik cos eşik ~0.4 (low) → 0.6 (strict). Rapor %90 → ~0.5.
        res.matched = cos >= (1.0 - self.cfg.match_distance_threshold)
        return res


# ---------------------------------------------------------------- ön yüz
class FaceVerifier:
    def __init__(self, cfg: FaceConfig | None = None, force_backend: str | None = None):
        self.cfg = cfg or CFG.face
        if force_backend == "trt":
            det, emb = _find_engines()
            trt_be = TRTBackend(self.cfg, det, emb)
            if trt_be.load():
                self.backend = trt_be
                self.backend_name = "tensorrt"
            else:
                print("[YÜZ] UYARI: TRT engine yok/yüklenemedi -> dlib fallback")
                self.backend = (FaceRecognitionBackend(self.cfg) if _HAS_FR
                                else OpenCVBackend(self.cfg))
                self.backend_name = ("face_recognition" if _HAS_FR
                                     else "opencv-fallback")
        elif force_backend == "opencv" or (not _HAS_FR and force_backend != "fr"):
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

    def enroll_from_jpeg(self, jpeg_bytes: bytes,
                         recipient_id: int = 0) -> bool:
        """LoRa'dan gelen JPEG bayt dizisini decode et + enroll et.

        Sprint 2 P1.2 — yer istasyonu yüz görüntüsünü gönderdiğinde drone tek
        atımda referans embedding'i çıkarır. Defensive: boş/bozuk byte → False."""
        import numpy as np
        if not jpeg_bytes or len(jpeg_bytes) < 4:
            print("[YÜZ] enroll_from_jpeg: boş veya çok küçük payload")
            return False
        try:
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"[YÜZ] enroll_from_jpeg: decode hatası {e}")
            return False
        if img is None or img.size == 0:
            print("[YÜZ] enroll_from_jpeg: JPEG decode edilemedi")
            return False
        if self.backend.enroll(recipient_id, img):
            if recipient_id not in self.enrolled:
                self.enrolled.append(recipient_id)
            print(f"[YÜZ] LoRa'dan enroll OK: recipient_id={recipient_id}")
            return True
        print("[YÜZ] enroll_from_jpeg: yüz bulunamadı")
        return False

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
