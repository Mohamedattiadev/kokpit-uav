"""
build_face_trt.py — ONNX → TensorRT engine builder for face pipeline.

Jetson Orin Nano üzerinde RetinaFace MobileNet 0.25 (detector) + ArcFace R50
(embedder) ONNX modellerini TRT engine'e dönüştürür. Engine cache key:
  {model}_{trt_version}_{jetpack}_{precision}.engine

Jetson olmadığında (tensorrt yok) graceful skip — exit code 0, mesaj.

Kullanım:
  python3 tools/build_face_trt.py \
      --detector models/retinaface_mnet025.onnx \
      --embedder models/arcface_r50.onnx \
      --out onboard/models --precision fp16

Çıktı:
  onboard/models/det_<trt>_<jp>_fp16.engine
  onboard/models/emb_<trt>_<jp>_fp16.engine
  onboard/models/.meta.json  (versiyon bilgisi)
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import re
import sys


def _detect_jetpack() -> str:
    p = "/etc/nv_tegra_release"
    if not os.path.exists(p):
        return "no-jetpack"
    try:
        with open(p) as f:
            head = f.readline().strip()
        # Dosya adı için güvenli hale getir: sadece alfanumerik + . + _ kalsın
        safe = re.sub(r"[^A-Za-z0-9._]+", "_", head)
        return safe.strip("_")[:32]
    except OSError:
        return "unknown"


def build_engine(onnx_path: str, out_path: str, precision: str = "fp16",
                 workspace_gb: int = 2,
                 fixed_shape: tuple[int, int, int, int] | None = None) -> bool:
    """ONNX → TRT engine. tensorrt yoksa False döner.

    fixed_shape: (N, C, H, W) — ONNX girişinde dinamik boyut (-1 / '?') varsa
    optimization profile bu sabit şekille (min=opt=max) oluşturulur. RetinaFace/
    ArcFace export'ları genelde dinamik H/W veya batch ile geldiği için TRT
    'no optimization profile' hatası vermeden derlenemez."""
    try:
        import tensorrt as trt  # type: ignore
    except Exception as e:
        print(f"[TRT] tensorrt import edilemedi ({e}); skip")
        return False
    if not os.path.exists(onnx_path):
        print(f"[TRT] ONNX yok: {onnx_path}")
        return False
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(
        1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    with open(onnx_path, "rb") as f:
        if not parser.parse(f.read()):
            for i in range(parser.num_errors):
                print(f"[TRT] parse hata: {parser.get_error(i)}")
            return False
    config = builder.create_builder_config()
    if fixed_shape is not None and network.num_inputs > 0:
        inp = network.get_input(0)
        if any(d == -1 for d in inp.shape):
            profile = builder.create_optimization_profile()
            profile.set_shape(inp.name, fixed_shape, fixed_shape, fixed_shape)
            config.add_optimization_profile(profile)
    if hasattr(config, "set_memory_pool_limit"):
        # TRT >= 8.5 API
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE,
                                     workspace_gb * (1 << 30))
    else:
        # TRT < 8.5 legacy API
        config.max_workspace_size = workspace_gb * (1 << 30)
    if precision == "fp16" and builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)
    if precision == "int8" and builder.platform_has_fast_int8:
        config.set_flag(trt.BuilderFlag.INT8)
    if hasattr(builder, "build_serialized_network"):
        # TRT >= 10.0 API — build_engine kaldırıldı
        serialized = builder.build_serialized_network(network, config)
        if serialized is None:
            print("[TRT] engine build başarısız")
            return False
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(serialized)
    else:
        engine = builder.build_engine(network, config)
        if engine is None:
            print("[TRT] engine build başarısız")
            return False
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(engine.serialize())
    print(f"[TRT] yazıldı: {out_path}")
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", help="RetinaFace ONNX path")
    ap.add_argument("--embedder", help="ArcFace ONNX path")
    ap.add_argument("--out", default="onboard/models", help="engine dir")
    ap.add_argument("--precision", default="fp16",
                    choices=["fp16", "fp32", "int8"])
    ap.add_argument("--det-size", type=int, default=640,
                    help="detector giriş H=W (face_verifier.TRTBackend.DET_INPUT ile eşleşmeli)")
    ap.add_argument("--emb-size", type=int, default=112,
                    help="embedder giriş H=W (TRTBackend.EMB_INPUT ile eşleşmeli)")
    args = ap.parse_args(argv)

    try:
        import tensorrt as trt  # type: ignore
        trt_ver = trt.__version__
    except Exception:
        print("[TRT] tensorrt yok; Jetson dışı ortamda skip.")
        return 0

    jp = _detect_jetpack()
    os.makedirs(args.out, exist_ok=True)
    meta = {
        "trt_version": trt_ver,
        "jetpack": jp,
        "precision": args.precision,
        "platform": platform.platform(),
    }
    ok_all = True
    if args.detector:
        out = os.path.join(args.out, f"det_{trt_ver}_{jp}_{args.precision}.engine")
        ok_all &= build_engine(args.detector, out, args.precision,
                               fixed_shape=(1, 3, args.det_size, args.det_size))
    if args.embedder:
        out = os.path.join(args.out, f"emb_{trt_ver}_{jp}_{args.precision}.engine")
        ok_all &= build_engine(args.embedder, out, args.precision,
                               fixed_shape=(1, 3, args.emb_size, args.emb_size))
    with open(os.path.join(args.out, ".meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
