"""
calibrate_camera.py — Kamera iç parametre (matris + distorsiyon) kalibrasyonu

Satranç tahtası (chessboard) desenli kareler kullanarak IMX219 kamerasını
kalibre eder ve sonucu camera_calibration.npz olarak kaydeder. aruco_detector
ve poz kestirimi bu dosyayı otomatik yükler (yoksa config varsayılanlarını kullanır).

HAZIRLIK:
  * 9x6 iç köşeli bir satranç tahtası yazdır (örn. A4, kare ~25 mm).
  * Tahtayı kameraya farklı açı/uzaklıklardan göster, ~20 kare yakala.

KULLANIM:
  # Canlı yakalama (boşlukla kare çek, q ile bitir):
  python3 calibrate_camera.py --live --cols 9 --rows 6 --square 0.025
  # Klasördeki hazır görüntülerden:
  python3 calibrate_camera.py --images "calib/*.jpg" --cols 9 --rows 6 --square 0.025

ÇIKTI: camera_calibration.npz  (camera_matrix, dist_coeffs)
"""
import argparse
import glob
import sys
import numpy as np
import cv2


def calibrate(image_list, cols, rows, square):
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square
    objpoints, imgpoints = [], []
    shape = None
    used = 0
    for img in image_list:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        shape = gray.shape[::-1]
        ok, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
        if not ok:
            continue
        corners = cv2.cornerSubPix(
            gray, corners, (11, 11), (-1, -1),
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
        objpoints.append(objp)
        imgpoints.append(corners)
        used += 1
    if used < 5:
        print(f"HATA: yeterli geçerli kare yok ({used}). En az 5-10 gerekir.")
        return None
    rms, mtx, dist, _, _ = cv2.calibrateCamera(
        objpoints, imgpoints, shape, None, None)
    print(f"Kullanılan kare: {used}, RMS yeniden-projeksiyon hatası: {rms:.4f}")
    print("camera_matrix:\n", mtx)
    print("dist_coeffs:", dist.ravel())
    return mtx, dist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--images", default=None, help="glob, örn 'calib/*.jpg'")
    ap.add_argument("--cols", type=int, default=9, help="iç köşe (yatay)")
    ap.add_argument("--rows", type=int, default=6, help="iç köşe (dikey)")
    ap.add_argument("--square", type=float, default=0.025, help="kare boyu (m)")
    ap.add_argument("--out", default="camera_calibration.npz")
    ap.add_argument("--device", type=int, default=0)
    args = ap.parse_args()

    images = []
    if args.live:
        cap = cv2.VideoCapture(args.device)
        print("BOŞLUK: kare yakala  |  q: bitir")
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.imshow("calib (BOSLUK yakala, q bitir)", frame)
            k = cv2.waitKey(1) & 0xFF
            if k == ord(" "):
                images.append(frame.copy())
                print(f"  yakalandı: {len(images)}")
            elif k == ord("q"):
                break
        cap.release()
        cv2.destroyAllWindows()
    elif args.images:
        for p in sorted(glob.glob(args.images)):
            im = cv2.imread(p)
            if im is not None:
                images.append(im)
    else:
        print("--live veya --images verin.")
        sys.exit(1)

    res = calibrate(images, args.cols, args.rows, args.square)
    if res is None:
        sys.exit(1)
    mtx, dist = res
    np.savez(args.out, camera_matrix=mtx, dist_coeffs=dist)
    print(f"Kaydedildi: {args.out}")
    print("Bu dosyayı onboard/ yanına koy; aruco_detector otomatik yükler.")


if __name__ == "__main__":
    main()
