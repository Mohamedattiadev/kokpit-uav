"""N8 — Live camera stream + ArUco overlay (jüri görünürlük).

Flask MJPEG. Frame producer alt thread, lock'lu son frame paylaşımı.
0.0.0.0:8080 bind (saha alanı). Basic auth env KOKPIT_DASH_PW ile.
"""
from __future__ import annotations
import os
import threading
import time
from functools import wraps
from typing import Callable, Optional

import numpy as np
from flask import Flask, Response, request, abort, jsonify

try:
    import cv2
except Exception:
    cv2 = None


app = Flask(__name__)

_last_frame_lock = threading.Lock()
_last_frame: Optional[bytes] = None  # JPEG bytes
_latest_status: dict = {}
_frame_producer_running = False


def _basic_auth_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        pw = os.environ.get("KOKPIT_DASH_PW")
        if not pw:
            return fn(*a, **kw)
        auth = request.authorization
        if not auth or auth.password != pw:
            return Response("auth required", 401,
                            {"WWW-Authenticate": 'Basic realm="kokpit"'})
        return fn(*a, **kw)
    return wrap


def update_frame(jpeg_bytes: bytes) -> None:
    global _last_frame
    with _last_frame_lock:
        _last_frame = jpeg_bytes


def update_status(d: dict) -> None:
    _latest_status.clear()
    _latest_status.update(d)
    _latest_status["ts"] = time.time()


def render_aruco_overlay(frame, corners=None, confidence: float = 0.0) -> bytes:
    """ArUco bbox + confidence yazı overlay'i JPEG byte olarak döndür."""
    if cv2 is None:
        return b""
    img = frame.copy()
    if corners is not None and len(corners) > 0:
        pts = np.array(corners[0]).astype(int).reshape(-1, 2)
        cv2.polylines(img, [pts], True, (0, 255, 0), 2)
    cv2.putText(img, f"conf={confidence:.2f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return buf.tobytes() if ok else b""


@app.route("/stream.mjpg")
@_basic_auth_required
def stream():
    def gen():
        while True:
            with _last_frame_lock:
                f = _last_frame
            if f:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + f + b"\r\n")
            time.sleep(0.04)  # ~25 FPS cap
    return Response(gen(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/status.json")
@_basic_auth_required
def status():
    return jsonify(_latest_status)


@app.route("/")
@_basic_auth_required
def index():
    return ("""<!doctype html><title>Kokpit Live</title>
<h1>Kokpit Live</h1>
<img src="/stream.mjpg" width="640"/>
<pre id="s"></pre>
<script>
setInterval(()=>fetch('/status.json').then(r=>r.json()).then(j=>
  document.getElementById('s').textContent=JSON.stringify(j,null,2)),1000);
</script>""")


def start_producer(frame_source: Callable, aruco_detect: Callable):
    """Background frame producer. Test'te çağırmaya gerek yok."""
    global _frame_producer_running
    _frame_producer_running = True

    def loop():
        while _frame_producer_running:
            try:
                frame = frame_source()
                if frame is None:
                    time.sleep(0.1); continue
                corners, conf = aruco_detect(frame)
                jpg = render_aruco_overlay(frame, corners, conf)
                if jpg:
                    update_frame(jpg)
            except Exception as e:
                print(f"[DASH] producer hatası: {e}")
                time.sleep(0.5)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def stop_producer():
    global _frame_producer_running
    _frame_producer_running = False


def main():
    port = int(os.environ.get("KOKPIT_DASH_PORT", "8080"))
    pw = os.environ.get("KOKPIT_DASH_PW")
    allow_open = os.environ.get("KOKPIT_DASH_ALLOW_OPEN") == "1"
    host = os.environ.get("KOKPIT_DASH_HOST", "0.0.0.0")
    if host == "0.0.0.0" and not pw and not allow_open:
        print("[DASH] HATA: 0.0.0.0 bind + auth yok. KOKPIT_DASH_PW set et "
              "veya KOKPIT_DASH_ALLOW_OPEN=1 (yarışma sahası). Çıkılıyor.")
        return 1
    if host == "0.0.0.0" and not pw:
        print("[DASH] UYARI: dashboard auth'suz açık (saha alanı). "
              "Production'da KOKPIT_DASH_PW kullan.")
    app.run(host=host, port=port)
    return 0


if __name__ == "__main__":
    main()
