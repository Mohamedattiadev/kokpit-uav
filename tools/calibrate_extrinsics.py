"""
calibrate_extrinsics.py — kamera + lidar mount offset interaktif kalibrasyon.

Kullanıcıdan cetvelle ölçü ister, onboard/configs/extrinsics.yaml dosyasına
yazar. Düz YAML alt-küme (bizim parser uyumlu).
"""
from __future__ import annotations
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "onboard",
                           "configs", "extrinsics.yaml")


def _ask(prompt: str, default: float) -> float:
    try:
        s = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return default
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        print("  geçersiz, default kullanıldı")
        return default


def main() -> int:
    print("Kokpit extrinsics kalibrasyonu (gövde: x=ileri, y=sağ, z=aşağı; m).")
    print("Sensörün gövde MERKEZİNE göre konumunu cetvelle ölç ve gir.\n")
    cam = {
        "x": _ask("CAM x (ileri)", 0.0),
        "y": _ask("CAM y (sağ)", 0.0),
        "z": _ask("CAM z (aşağı)", 0.10),
        "roll": _ask("CAM roll deg", 0.0),
        "pitch": _ask("CAM pitch deg", 0.0),
        "yaw": _ask("CAM yaw deg", 0.0),
    }
    lid = {
        "x": _ask("LIDAR x (ileri)", 0.05),
        "y": _ask("LIDAR y (sağ)", 0.0),
        "z": _ask("LIDAR z (aşağı)", 0.05),
        "roll": _ask("LIDAR roll deg", 0.0),
        "pitch": _ask("LIDAR pitch deg", 0.0),
        "yaw": _ask("LIDAR yaw deg", 0.0),
    }
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        f.write("# extrinsics.yaml — calibrate_extrinsics.py tarafından üretildi\n")
        f.write("cam_to_body:\n")
        for k, v in cam.items():
            f.write(f"  {k}: {v}\n")
        f.write("lidar_to_body:\n")
        for k, v in lid.items():
            f.write(f"  {k}: {v}\n")
    print(f"\nYazıldı: {CONFIG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
