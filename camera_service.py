#!/usr/bin/env python3
"""
Rover camera service: one process owns the Pi camera, rotates frames 180 deg once,
and shares them between an MJPEG stream and a cabinet-marker detector.

Routes (port 8000):
  GET /stream.mjpg    live MJPEG feed (open in a browser)
  GET /snapshot.jpg   latest upright JPEG
  GET /detections     JSON: frame timestamp (UTC) + visible markers with image_x_norm
  GET /health         JSON: fps, frame age, camera source
  GET /               tiny page showing the stream

Run on the rover:   python3 camera_service.py
Laptop test:        python3 camera_service.py --source webcam     (or --source image:tag.png)
"""
import argparse
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

# ---------------------------------------------------------------- settings
TAG_TO_CABINET = {1: "rack-01", 2: "rack-02"}
# Fallback colored stickers (HSV ranges) -> cabinet, used with --markers color or both
COLOR_TO_CABINET = {
    "green": {"cabinet": "rack-01", "lo": (45, 80, 60), "hi": (85, 255, 255)},
    "magenta": {"cabinet": "rack-02", "lo": (140, 80, 60), "hi": (170, 255, 255)},
}
MIN_COLOR_AREA = 600          # px, ignore specks


class Shared:
    """Latest frame, its JPEG and its detections, produced together by one thread."""

    def __init__(self):
        self.cond = threading.Condition()
        self.jpeg = None
        self.frame_id = 0
        self.ts_iso = None
        self.ts_mono = 0.0
        self.detections = []
        self.size = (0, 0)
        self.fps = 0.0


S = Shared()


# ---------------------------------------------------------------- camera sources
class PiCamera:
    def __init__(self, w, h, rotate):
        from libcamera import Transform
        from picamera2 import Picamera2
        self.cam = Picamera2()
        tf = Transform(hflip=True, vflip=True) if rotate else Transform()
        cfg = self.cam.create_video_configuration(main={"size": (w, h), "format": "RGB888"}, transform=tf)
        self.cam.configure(cfg)
        self.cam.start()
        time.sleep(1.0)

    def read(self):
        # Picamera2 "RGB888" is laid out B,G,R in memory = what OpenCV expects
        return self.cam.capture_array("main")


class OpenCVSource:
    def __init__(self, spec, w, h, rotate):
        self.rotate = rotate
        if spec.startswith("image:"):
            self.still = cv2.imread(spec[6:])
            if self.still is None:
                raise SystemExit(f"cannot read {spec[6:]}")
            self.cap = None
        else:
            self.cap = cv2.VideoCapture(0)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

    def read(self):
        if self.cap is None:
            time.sleep(1 / 15)
            f = self.still.copy()
        else:
            ok, f = self.cap.read()
            if not ok:
                return None
        return cv2.rotate(f, cv2.ROTATE_180) if self.rotate else f


# ---------------------------------------------------------------- detectors
def make_apriltag_detector():
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG
    return cv2.aruco.ArucoDetector(d, p)


def detect_apriltags(det, gray, w, pan_deg):
    out = []
    corners, ids, _ = det.detectMarkers(gray)
    if ids is None:
        return out
    for c, i in zip(corners, ids.flatten()):
        pts = c.reshape(4, 2)
        cx, cy = pts.mean(axis=0)
        side = float(np.mean([np.linalg.norm(pts[k] - pts[(k + 1) % 4]) for k in range(4)]))
        out.append({
            "marker_type": "apriltag_36h11",
            "marker_id": int(i),
            "cabinet_id": TAG_TO_CABINET.get(int(i)),        # null for tags we don't map
            "image_x_norm": round(float((cx - w / 2) / (w / 2)), 3),
            "image_y_norm": round(float((cy - gray.shape[0] / 2) / (gray.shape[0] / 2)), 3),
            "size_px": round(side, 1),                       # bigger = closer
            "pan_deg": pan_deg,
        })
    return out


def detect_colors(bgr, w, pan_deg):
    out = []
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    for name, c in COLOR_TO_CABINET.items():
        m = cv2.inRange(hsv, np.array(c["lo"]), np.array(c["hi"]))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        big = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(big)
        if area < MIN_COLOR_AREA:
            continue
        x, y, bw, bh = cv2.boundingRect(big)
        cx = x + bw / 2
        out.append({
            "marker_type": "color",
            "marker_id": name,
            "cabinet_id": c["cabinet"],
            "image_x_norm": round(float((cx - w / 2) / (w / 2)), 3),
            "image_y_norm": round(float((y + bh / 2 - bgr.shape[0] / 2) / (bgr.shape[0] / 2)), 3),
            "size_px": round(float(np.sqrt(area)), 1),
            "pan_deg": pan_deg,
        })
    return out


# ---------------------------------------------------------------- capture loop
def capture_loop(src, args):
    det = make_apriltag_detector()
    n, t0 = 0, time.time()
    while True:
        frame = src.read()
        if frame is None:
            time.sleep(0.05)
            continue
        h, w = frame.shape[:2]
        dets = []
        if args.markers in ("apriltag", "both"):
            dets += detect_apriltags(det, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), w, args.pan_deg)
        if args.markers in ("color", "both"):
            dets += detect_colors(frame, w, args.pan_deg)
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
        if not ok:
            continue
        with S.cond:
            S.jpeg = jpg.tobytes()
            S.frame_id += 1
            S.ts_iso = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            S.ts_mono = time.monotonic()
            S.detections = dets
            S.size = (w, h)
            S.cond.notify_all()
        n += 1
        if time.time() - t0 >= 2:
            S.fps = round(n / (time.time() - t0), 1)
            n, t0 = 0, time.time()


# ---------------------------------------------------------------- HTTP
PAGE = b"""<!doctype html><html><head><title>Rover camera</title>
<style>body{background:#111;color:#ddd;font-family:sans-serif;text-align:center}img{max-width:95vw}</style></head>
<body><h3>Rover camera</h3><img src="/stream.mjpg"><p><a href="/detections">/detections</a> &middot;
<a href="/snapshot.jpg">/snapshot.jpg</a> &middot; <a href="/health">/health</a></p></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")    # CS dashboard can fetch it
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, "text/html", PAGE)
        if path == "/detections":
            with S.cond:
                body = {
                    "frame_id": S.frame_id,
                    "timestamp_utc": S.ts_iso,
                    "frame_age_s": round(time.monotonic() - S.ts_mono, 3) if S.ts_iso else None,
                    "image_size": list(S.size),
                    "detections": S.detections,
                }
            return self._send(200, "application/json", json.dumps(body).encode())
        if path == "/snapshot.jpg":
            with S.cond:
                jpg = S.jpeg
            return self._send(200, "image/jpeg", jpg) if jpg else self._send(503, "text/plain", b"no frame yet")
        if path == "/health":
            with S.cond:
                body = {"fps": S.fps, "frame_id": S.frame_id, "timestamp_utc": S.ts_iso,
                        "frame_age_s": round(time.monotonic() - S.ts_mono, 3) if S.ts_iso else None}
            return self._send(200, "application/json", json.dumps(body).encode())
        if path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            last = -1
            try:
                while True:
                    with S.cond:
                        S.cond.wait_for(lambda: S.frame_id != last, timeout=2.0)
                        jpg, last = S.jpeg, S.frame_id
                    if jpg is None:
                        continue
                    self.wfile.write(b"--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                return
        return self._send(404, "text/plain", b"not found")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="picamera", help="picamera | webcam | image:<file>")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--no-rotate", action="store_true", help="use if the boot config already flips the image")
    ap.add_argument("--markers", default="apriltag", choices=["apriltag", "color", "both"])
    ap.add_argument("--pan-deg", type=float, default=None, help="camera pan angle if known (0 = centred)")
    ap.add_argument("--quality", type=int, default=75)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    rotate = not args.no_rotate
    src = PiCamera(args.width, args.height, rotate) if args.source == "picamera" \
        else OpenCVSource(args.source, args.width, args.height, rotate)
    threading.Thread(target=capture_loop, args=(src, args), daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    srv.daemon_threads = True
    print(f"camera service on :{args.port}  ->  /stream.mjpg  /detections  /snapshot.jpg")
    srv.serve_forever()


if __name__ == "__main__":
    main()
