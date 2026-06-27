# 04 — YÜZ TANIMA (TensorRT Biyometrik Doğrulama)

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `Promptlar/03_jetson_mission_computer.md` (EventBus + MissionState API)

## Görev
Jetson Orin Nano üzerinde TensorRT hızlandırmalı yüz tanıma modülü. İki kullanım:
1. **Tetikleme anında (yer ünitesinden gelen yüz)**: ESP32'den gelen JPEG'i decode et, embedding çıkar, `MissionState.ref_embedding`'e koy.
2. **Teslimat anında (İHA kamerasından canlı)**: IMX219 frame'lerinde yüz tespit et, embedding çıkar, ref ile cosine similarity > eşik → `face_verified = True`.

## Açılışta Executor'a Sor (zorunlu)

1. **Model**:
   - (a) **InsightFace ArcFace R50** (tavsiye — SOTA, 512-d embedding, MS1MV3 pretrained)
   - (b) FaceNet (Inception-ResNet-v1)
   - (c) `face_recognition` (dlib, CPU only — Jetson GPU kullanmaz, tavsiye etmem)
2. **Detector**:
   - (a) **RetinaFace MobileNet 0.25** (tavsiye, hızlı, küçük)
   - (b) SCRFD
   - (c) YuNet (OpenCV DNN)
3. **TensorRT precision**: FP16 (tavsiye — Orin Nano'da 2x hız, doğrulukta kayıp <%1) mi, INT8 mi (kalibrasyon dataset gerekir), FP32 mi?
4. **Hedef FPS** canlı verifikasyon için: 10 FPS yeterli (hover'da 1 sn'de 10 örnek). Onay?
5. **Eşleşme eşiği**: cosine sim > 0.50 (ArcFace tipik) mi, 0.40 mı? *(Rapor %90 doğruluk diyor — eşik tuningi test datası gerektirir)*
6. **Multi-frame verification**: Tek frame yeterli mi, 5 ardışık frame'in 4'ü geçerse onay mı (tavsiye, false-positive azaltır)?
7. **Referans yüz veri seti**: Yarışmada alıcı önceden mi enroll edilir, yoksa tetikleme anında ESP32'nin yolladığı tek yüz mü "altın referans" olur? *(Rapor ikincisini ima ediyor)*

## Mimari

```
jetson/mission_computer/src/kokpit/face_recognition/
├── __init__.py
├── detector.py          # RetinaFace ONNX → TensorRT engine
├── embedder.py          # ArcFace ONNX → TensorRT engine
├── verifier.py          # Pipeline orchestrator (asyncio task)
├── engines/             # .engine dosyaları (.gitignore)
└── models/              # .onnx dosyaları (.gitignore — büyük)
```

## Fonksiyonel Akış

### 1. Engine Hazırlama (boot-time, bir kez)
- `.onnx` → TensorRT `.engine` build (FP16)
- Build cache `engines/{model}_{precision}_{trt_version}.engine`
- Build süresi ~2 dk; build edilmişse skip

### 2. Referans Embedding (LoRa trigger geldiğinde)
```python
async def on_trigger(payload: TriggerPayload):
    img = cv2.imdecode(np.frombuffer(payload.jpeg, np.uint8), cv2.IMREAD_COLOR)
    faces = detector.detect(img)
    if len(faces) != 1:
        await event_bus.publish("face.ref_failed", "ref_face_count != 1")
        return
    aligned = align_face(img, faces[0].landmarks)  # 5-point similarity transform
    embedding = embedder.embed(aligned)  # (512,) L2-normalized
    state.ref_embedding = embedding
    await event_bus.publish("face.ref_ready", None)
```

### 3. Canlı Doğrulama (VERIFYING fazında)
```python
async def verify_loop():
    consecutive_ok = 0
    async for frame in camera_stream:
        if state.phase != MissionPhase.VERIFYING:
            consecutive_ok = 0
            continue
        faces = detector.detect(frame)
        if not faces:
            consecutive_ok = 0
            continue
        # Çerçeveye en yakın (alan max) yüzü seç
        face = max(faces, key=lambda f: f.area)
        aligned = align_face(frame, face.landmarks)
        emb = embedder.embed(aligned)
        sim = cosine_similarity(emb, state.ref_embedding)
        if sim >= cfg.face_match_threshold:
            consecutive_ok += 1
            if consecutive_ok >= cfg.face_match_frames:  # default 4
                state.face_verified = True
                await event_bus.publish("face.verified", sim)
                return
        else:
            consecutive_ok = 0
```

### 4. Liveness (BONUS, opsiyonel — executor sorsun)
- Blink detection / texture analysis (2D fotoğraf saldırısı önleme)
- Yarışma kapsamı şart koşmuyorsa skip

## Performans Hedefleri
- Detector: ≤ 30 ms / frame @ 720p FP16
- Embedder: ≤ 15 ms / yüz FP16
- Pipeline: ≥ 10 FPS sürdürülebilir
- Cold start (engine load): < 5 sn
- VRAM: < 1.5 GB

## Testler
- `test_detector.py`: bilinen yüzlü görselde tespit
- `test_embedder.py`: aynı kişinin 2 farklı fotoğrafında cosine > 0.5
- `test_embedder.py`: farklı kişiler cosine < 0.3
- `test_verifier.py`: mock state + mock kamera frame stream → verified path
- `test_engine_build.py`: ONNX'ten engine build smoke

## Veri
- `data/test_faces/`: 5 kişi × 5 foto (CI test için, `.gitignore` veya Git LFS)
- ArcFace model: `https://github.com/deepinsight/insightface` modellerini executor onaylayınca indir

## Kabul Kriterleri
- LFW benchmark ≥ %99 (model doğrulama)
- Yarışma testinde farklı ışıkta ≥ %90 doğru tanıma, ≤ %1 false-accept
- 30 dakika sürekli inference, VRAM stable, sızıntı yok

## GÜÇLENDİRMELER (AUDIT)

### G1. Engine Cache Versiyon Key
```
engines/{model}_{precision}_{trt_version}_{jetpack_version}.engine
```
TRT version / JetPack upgrade → otomatik rebuild. Yanlış engine load = silent crash.

### G2. Embedding-only Trigger Mode (opsiyonel)
Eğer ESP32 tarafı embed çıkarabilirse (modül 02 G3 `MSG_REF_EMBEDDING`), JPEG decode atla, direkt ref_embedding al. LoRa süresi 30 sn → 1 sn.

### G3. Pre-arm Engine Load Check
Modül 03 G1 prearm: `face.engines_loaded` flag. Boot'ta ilk dummy inference koş (warm-up + cache).

### G4. Multi-Scale Detection
RetinaFace input 320×320 default; küçük yüz için 640×640 cascade. Hover irtifa 1.5 m'de yüz ~80–120 px → 320×320 yeterli, ama emniyet için fallback rescale.

### G5. Optional Liveness (basit)
2 ardışık frame'de yüz pozisyonu hiç değişmiyor + arka plan da değişmiyor → potansiyel 2D fotoğraf. Threshold optical flow magnitude < 0.1 px → reject. Tek yarışma kapsamı için executor karar versin.

## Verme
- Çalışan modül, EventBus'a wire'lı
- `download_models.sh` script
- README: model lisansları, hangi datasette eğitildiği, eşik tuning rehberi
- Benchmark raporu (`benchmark.py` çıktısı)
