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
import sys


def _detect_jetpack() -> str:
    p = "/etc/nv_tegra_release"
    if not os.path.exists(p):
        return "no-jetpack"
    try:
        with open(p) as f:
            head = f.readline().strip()
        return head.replace(" ", "_")[:32]
    except OSError:
        return "unknown"


def build_engine(onnx_path: str, out_path: str, precision: str = "fp16",
                 workspace_gb: int = 2) -> bool:
    """ONNX → TRT engine. tensorrt yoksa False döner."""
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
    config.max_workspace_size = workspace_gb * (1 << 30)
    if precision == "fp16" and builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)
    if precision == "int8" and builder.platform_has_fast_int8:
        config.set_flag(trt.BuilderFlag.INT8)
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
        ok_all &= build_engine(args.detector, out, args.precision)
    if args.embedder:
        out = os.path.join(args.out, f"emb_{trt_ver}_{jp}_{args.precision}.engine")
        ok_all &= build_engine(args.embedder, out, args.precision)
    with open(os.path.join(args.out, ".meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
