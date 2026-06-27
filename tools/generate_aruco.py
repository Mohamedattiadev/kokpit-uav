"""
generate_aruco.py — Yer ünitesi (ped) için yazdırılabilir ArUco marker üretir.

Kullanım:
    python3 generate_aruco.py --id 0 --dict DICT_5X5_100 --size 800 --out ped_marker.png

Üretilen PNG'yi config.aruco.marker_length_m ile AYNI fiziksel kenar uzunluğunda
yazdır (örn. 30 cm). Marker kenarına beyaz "quiet zone" (sessiz bölge) bırak.
"""
import argparse
import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, default=0)
    ap.add_argument("--dict", default="DICT_5X5_100")
    ap.add_argument("--size", type=int, default=800, help="piksel kenar")
    ap.add_argument("--border", type=int, default=80, help="beyaz kenar (px)")
    ap.add_argument("--out", default="ped_marker.png")
    args = ap.parse_args()

    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, args.dict))
    if hasattr(cv2.aruco, "generateImageMarker"):
        marker = cv2.aruco.generateImageMarker(dictionary, args.id, args.size)
    else:
        marker = cv2.aruco.drawMarker(dictionary, args.id, args.size)

    canvas = np.full((args.size + 2 * args.border,
                      args.size + 2 * args.border), 255, dtype=np.uint8)
    canvas[args.border:args.border + args.size,
           args.border:args.border + args.size] = marker
    cv2.imwrite(args.out, canvas)
    print(f"Yazıldı: {args.out}  (ID={args.id}, dict={args.dict})")
    print("Yazdırırken fiziksel kenarı config.aruco.marker_length_m ile eşitle.")


if __name__ == "__main__":
    main()
