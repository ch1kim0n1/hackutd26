#!/usr/bin/env python3
"""Rover-side inspect_cabinet mission service for the PiCar-X.

Speaks the contract HttpHardwareTransport uses
(robotics/rover/src/rover_mission/hw_adapter.py):

  POST /missions                 {mission_id, action: "inspect_cabinet", cabinet_id}
                                 -> 202 {mission_id, cabinet_id, state}
  GET  /missions/<id>            -> {mission_id, cabinet_id, state, error?, report?}
                                    (each poll is the supervisor heartbeat)
  POST /missions/<id>/abort      -> stop now
  POST /stop                     -> stop whatever is running
  GET  /missions/<id>/photo.jpg  -> evidence photo
  GET  /health                   (no token)

Every other route needs "Authorization: Bearer $ROVER_AUTONOMY_TOKEN".
The server binds 127.0.0.1 only; reach it through an SSH tunnel.

Mission: pan-camera sweep for the cabinet's AprilTag (no wheel motion) ->
optional guarded approach (motion_enabled) -> verify tag, take photo,
probe ONLY that cabinet's registered Pi -> report.

Wheels turn only while ALL hold: a mission is running, the supervisor polled
within supervision_s, the mission deadline has not passed, the LiDAR has a
fresh clear forward scan, the tag is freshly in view, and the worker renewed
the deadman within deadman_s. A separate safety thread enforces the deadman,
so a stuck worker still stops. A hard kill (SIGKILL, power loss of the Pi
only) cannot run code: the physical E-stop remains the last line.
"""
import argparse
import hashlib
import hmac
import json
import math
import os
import re
import signal
import socket
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

# Calibration knobs; override any of them in the JSON config.
DEFAULTS = {
    "camera_url": "http://127.0.0.1:18080",
    "evidence_dir": "~/blindspot-evidence",
    "motion_enabled": False,        # False = look + photograph + probe from where it stands
    "supervision_s": 2.0,           # abort if the supervisor stops polling
    "mission_s": 28.0,              # hard deadline (client timeout is capped at 30 s)
    "deadman_s": 0.25,              # safety thread stops motors if worker goes quiet
    "scan_timeout_s": 0.30,
    "stop_m": 0.45,                 # forward clearance, measured from the LiDAR
    "half_width_m": 0.16,
    "power": 12,                    # Picarx motor power, not m/s
    "pan_sweep_deg": [0, -20, 20, -40, 40, -60, 60],
    "pan_settle_s": 0.5,
    "pan_sign": 1,                  # flip if a tag on the right reports a left bearing
    "hfov_deg": 62.0,
    "approach_cone_deg": 30.0,      # Ackermann can't turn in place: only approach tags roughly ahead
    "approach_s": 15.0,
    "steer_gain": 1.0,
    "steer_trim_deg": 0.0,          # set from a straight-line drive test
    "max_steer_deg": 30.0,
    "arrive_px": 90.0,              # tag side length that counts as "at the cabinet"
    "near_px": 55.0,                # LiDAR stop with a tag this big = the cabinet itself
    "lost_s": 1.0,
    "det_max_age_s": 0.35,
    "probe_timeout_s": 1.0,
    "cabinets": {},                 # {"rack-02": {"tag_id": 2, "device_id": "pi-02", "host": "...", "tcp_ports": [22]}}
}

MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
ACTIVE = {"accepted", "searching", "target_found", "inspecting"}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def assess(scan, stop_m, half_width_m):
    """Forward corridor check (same rule as guarded_drive.py)."""
    angles, ranges = scan
    valid = np.isfinite(ranges) & (ranges > 0)
    for lo, hi in [(-20, -6), (-6, 6), (6, 20)]:
        sector = (angles >= math.radians(lo)) & (angles < math.radians(hi))
        if np.count_nonzero(valid & sector) < 2:
            return "missing forward coverage"
    forward = ranges * np.cos(angles)
    side = ranges * np.sin(angles)
    blocked = valid & (forward > 0) & (forward <= stop_m) & (np.abs(side) <= half_width_m)
    if blocked.any():
        return f"obstacle {forward[blocked].min():.2f} m ahead"
    return "clear"


class CameraClient:
    """Reads the camera service (camera_service.py) that owns the Pi camera."""

    def __init__(self, base):
        self.base = base.rstrip("/")

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=1.0) as r:
            return r.read(4 * 1024 * 1024)

    def detections(self):
        return json.loads(self._get("/detections"))

    def snapshot(self):
        return self._get("/snapshot.jpg")


def tcp_probe(host, port, timeout):
    t = time.monotonic()
    try:
        socket.create_connection((host, int(port)), timeout=timeout).close()
        return {"name": f"tcp_{port}", "ok": True,
                "latency_ms": int((time.monotonic() - t) * 1000), "detail": host}
    except OSError as exc:
        return {"name": f"tcp_{port}", "ok": False,
                "latency_ms": int((time.monotonic() - t) * 1000),
                "detail": f"{host}: {exc.__class__.__name__}"}


class Abort(Exception):
    pass


class Fail(Exception):
    pass


class Mission:
    def __init__(self, mission_id, cabinet_id, deadline, clock):
        self.id, self.cabinet_id = mission_id, cabinet_id
        self.state, self.error, self.report = "accepted", None, None
        self.started = now_iso()
        self.deadline = deadline
        self.last_poll = clock()
        self.abort_reason = None
        self.photo = None

    def view(self):
        out = {"mission_id": self.id, "cabinet_id": self.cabinet_id, "state": self.state}
        if self.error:
            out["error"] = self.error
        if self.report:
            out["report"] = self.report
        return out


class MissionService:
    def __init__(self, cfg, car, lidar, camera, probe=tcp_probe, clock=time.monotonic):
        self.cfg = {**DEFAULTS, **cfg}
        self.car, self.lidar, self.camera, self.probe, self.clock = car, lidar, camera, probe, clock
        self.lock = threading.Lock()          # mission table
        self.car_lock = threading.Lock()      # single motor/servo owner
        self.missions = {}
        self.active = None
        self.drive_until = 0.0
        self.alive = True
        threading.Thread(target=self._safety_loop, daemon=True).start()

    # -- motors ---------------------------------------------------------------
    def stop(self):
        with self.car_lock:
            self.drive_until = 0.0
            self.car.stop()

    def _drive(self, steer):
        with self.car_lock:
            self.car.set_dir_servo_angle(steer)
            self.drive_until = self.clock() + self.cfg["deadman_s"]
            self.car.forward(self.cfg["power"])

    def _servo(self, fn, angle):
        with self.car_lock:
            getattr(self.car, fn)(angle)

    def _safety_loop(self):
        while self.alive:
            with self.car_lock:
                if self.drive_until and self.clock() > self.drive_until:
                    self.drive_until = 0.0
                    self.car.stop()
            time.sleep(0.02)

    # -- API ------------------------------------------------------------------
    def submit(self, body):
        if not isinstance(body, dict) or body.get("action") != "inspect_cabinet":
            return 400, {"error": "action must be inspect_cabinet"}
        mid, cab = body.get("mission_id"), body.get("cabinet_id")
        if not isinstance(mid, str) or not MISSION_ID.match(mid):
            return 400, {"error": "bad mission_id"}
        if cab not in self.cfg["cabinets"]:
            return 400, {"error": "cabinet_id not registered"}
        with self.lock:
            old = self.missions.get(mid)
            if old:
                if old.cabinet_id != cab:
                    return 409, {"error": "mission_id reused for another cabinet"}
                old.last_poll = self.clock()
                return 200, old.view()
            if self.active and self.active.state in ACTIVE:
                return 409, {"error": f"busy with {self.active.id}"}
            m = Mission(mid, cab, self.clock() + self.cfg["mission_s"], self.clock)
            self.missions[mid] = self.active = m
            for k in list(self.missions)[:-50]:
                self.missions.pop(k)
            view = m.view()
        threading.Thread(target=self._run, args=(m,), daemon=True).start()
        return 202, view

    def poll(self, mid):
        with self.lock:
            m = self.missions.get(mid)
            if not m:
                return 404, {"error": "unknown mission"}
            m.last_poll = self.clock()
            return 200, m.view()

    def abort(self, mid=None, reason="operator_abort"):
        with self.lock:
            m = self.missions.get(mid) if mid else self.active
            if m and m.state in ACTIVE:
                m.abort_reason = reason
        self.stop()
        if mid and not m:
            return 404, {"error": "unknown mission"}
        return 200, (m.view() if m else {"state": "idle"})

    # -- mission --------------------------------------------------------------
    def _guard(self, m):
        if m.abort_reason:
            raise Abort(m.abort_reason)
        now = self.clock()
        if now - m.last_poll > self.cfg["supervision_s"]:
            raise Abort("supervision_lost")
        if now > m.deadline:
            raise Abort("mission_timeout")

    def _wait(self, m, seconds):
        end = self.clock() + seconds
        while self.clock() < end:
            self._guard(m)
            time.sleep(0.02)

    def _forward_clear(self):
        scan, stamp = self.lidar.get(0)
        if scan is None or time.time() - stamp > self.cfg["scan_timeout_s"]:
            return "stale scan"
        return assess(scan, self.cfg["stop_m"], self.cfg["half_width_m"])

    def _tag(self, tag_id):
        """Fresh detection of exactly this tag, else None."""
        try:
            d = self.camera.detections()
        except Exception:
            return None
        age = d.get("frame_age_s")
        if age is None or age > self.cfg["det_max_age_s"]:
            return None
        for det in d.get("detections", []):
            if det.get("marker_type") == "apriltag_36h11" and det.get("marker_id") == tag_id:
                return det
        return None

    def _run(self, m):
        cab = self.cfg["cabinets"][m.cabinet_id]
        try:
            m.state = "searching"
            pan, det = self._search(m, cab["tag_id"])
            m.state = "target_found"
            if self.cfg["motion_enabled"]:
                self._approach(m, cab["tag_id"], pan, det)
            m.state = "inspecting"
            m.report = self._inspect(m, cab)
            m.state = "completed"
        except Abort as exc:
            m.state, m.error = "aborted", str(exc)
        except Fail as exc:
            m.state, m.error = "failed", str(exc)
        except Exception as exc:  # never leave motors running on a bug
            m.state, m.error = "failed", f"internal:{exc.__class__.__name__}"
        finally:
            self.stop()

    def _search(self, m, tag_id):
        """Camera-only sweep; the wheels do not move."""
        for pan in self.cfg["pan_sweep_deg"]:
            self._guard(m)
            self._servo("set_cam_pan_angle", pan)
            self._wait(m, self.cfg["pan_settle_s"])
            det = self._tag(tag_id)
            if det:
                return pan, det
        self._servo("set_cam_pan_angle", 0)
        raise Fail("target_not_found")

    def _approach(self, m, tag_id, pan, det):
        c = self.cfg
        bearing = pan * c["pan_sign"] + det["image_x_norm"] * c["hfov_deg"] / 2
        if abs(bearing) > c["approach_cone_deg"]:
            raise Fail(f"target_outside_approach_cone:{bearing:.0f}deg")
        self._servo("set_cam_pan_angle", 0)
        self._wait(m, c["pan_settle_s"])
        end = self.clock() + c["approach_s"]
        last_seen = self.clock()
        while True:
            self._guard(m)
            now = self.clock()
            det = self._tag(tag_id)
            clear = self._forward_clear()
            size = det["size_px"] if det else 0.0
            if size >= c["arrive_px"] or (clear.startswith("obstacle") and size >= c["near_px"]):
                self.stop()
                return
            if det:
                last_seen = now
            elif now - last_seen > c["lost_s"]:
                raise Fail("target_lost")
            if now > end:
                raise Fail(f"approach_timeout:{clear}")
            if det and clear == "clear":
                x = det["image_x_norm"] * c["hfov_deg"] / 2 * c["steer_gain"]
                steer = max(-c["max_steer_deg"], min(c["max_steer_deg"], x + c["steer_trim_deg"]))
                self._drive(steer)
            else:
                self.stop()
            time.sleep(0.05)

    def _inspect(self, m, cab):
        tag_id = cab["tag_id"]
        before = self._tag(tag_id)
        try:
            jpg = self.camera.snapshot()
        except Exception:
            jpg = None
        after = self._tag(tag_id)
        self._guard(m)
        tag_ok = bool(before and after and jpg)
        checks = [{"name": "cabinet_tag", "ok": tag_ok, "latency_ms": 0,
                   "detail": f"apriltag_36h11 id={tag_id} size_px={(after or {}).get('size_px')}"}]
        evidence = []
        if jpg:
            out = Path(self.cfg["evidence_dir"]).expanduser() / m.id
            out.mkdir(parents=True, exist_ok=True)
            (out / "photo.jpg").write_bytes(jpg)
            sha = hashlib.sha256(jpg).hexdigest()
            m.photo = out / "photo.jpg"
            evidence.append({"kind": "photo", "ref": f"rover-01:evidence/{m.id}/photo.jpg", "sha256": sha})
        if not tag_ok:
            status, detail = "error", "target_tag_not_verified"
        else:
            # Probe ONLY the registered Pi for this cabinet, nothing else.
            for port in cab.get("tcp_ports", []):
                self._guard(m)
                checks.append(self.probe(cab["host"], port, self.cfg["probe_timeout_s"]))
            probes = checks[1:]
            ok = sum(c["ok"] for c in probes)
            status = "ok" if ok == len(probes) else "degraded" if ok else "unreachable"
            detail = f"{ok}/{len(probes)} probes ok"
        report = {
            "mission_id": m.id, "cabinet_id": m.cabinet_id,
            "target_device_id": cab.get("device_id", ""),
            "status": status, "detail": detail, "checks": checks, "evidence": evidence,
            "started_at": m.started, "completed_at": now_iso(),
            "motion_enabled": bool(self.cfg["motion_enabled"]),
            "provenance": "LIVE", "synthetic": False,
        }
        if m.photo:
            (m.photo.parent / "report.json").write_text(json.dumps(report, indent=2))
        return report


def make_handler(svc, token):
    expected = f"Bearer {token}".encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _authed(self):
            got = self.headers.get("authorization", "").encode()
            if hmac.compare_digest(got, expected):
                return True
            self._send(401, {"error": "unauthorized"})
            return False

        def do_GET(self):
            parts = self.path.split("?")[0].strip("/").split("/")
            if parts == ["health"]:
                a = svc.active
                return self._send(200, {"ok": True, "active": a.view() if a and a.state in ACTIVE else None,
                                        "lidar": svc._forward_clear()})
            if not self._authed():
                return
            if len(parts) == 2 and parts[0] == "missions":
                return self._send(*svc.poll(parts[1]))
            if len(parts) == 3 and parts[0] == "missions" and parts[2] == "photo.jpg":
                m = svc.missions.get(parts[1])
                if m and m.photo and m.photo.exists():
                    return self._send(200, m.photo.read_bytes(), "image/jpeg")
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authed():
                return
            parts = self.path.split("?")[0].strip("/").split("/")
            if parts == ["stop"]:
                return self._send(*svc.abort(None, "operator_stop"))
            if len(parts) == 3 and parts[0] == "missions" and parts[2] == "abort":
                return self._send(*svc.abort(parts[1]))
            if parts == ["missions"]:
                n = int(self.headers.get("content-length") or 0)
                if n > 4096:
                    return self._send(413, {"error": "too large"})
                try:
                    body = json.loads(self.rfile.read(n) or b"null")
                except ValueError:
                    return self._send(400, {"error": "bad json"})
                return self._send(*svc.submit(body))
            return self._send(404, {"error": "not found"})

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="mission JSON (cabinets + knobs)")
    ap.add_argument("--port", type=int, default=18090)
    args = ap.parse_args()
    token = os.environ.get("ROVER_AUTONOMY_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("ROVER_AUTONOMY_TOKEN missing or shorter than 16 chars")
    cfg = json.loads(Path(args.config).read_text())

    import yaml
    from lidar import SerialLidar
    from picarx import Picarx

    here = Path(__file__).resolve().parent
    lc = yaml.safe_load((here / "config.yaml").read_text())["lidar"]
    car = Picarx()
    car.stop()
    car.set_dir_servo_angle(0)
    car.set_cam_pan_angle(0)
    svc = MissionService(cfg, car, SerialLidar(lc["port"], lc["baud"], lc["mount_offset_deg"], lc["clockwise"]),
                         CameraClient(cfg.get("camera_url", DEFAULTS["camera_url"])))
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(svc, token))
    srv.daemon_threads = True
    print(f"mission service on 127.0.0.1:{args.port} motion_enabled={svc.cfg['motion_enabled']}", flush=True)
    try:
        srv.serve_forever()
    finally:
        svc.alive = False
        car.stop()
        car.set_dir_servo_angle(0)


if __name__ == "__main__":
    main()
