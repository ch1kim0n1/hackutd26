"""Safety + contract checks for mission_service.py with fake hardware.

Run: cd hardware/picarx/autonomy && python3 -m pytest -q test_mission_service.py
"""
import json
import math
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np

from mission_service import MissionService, make_handler

TOKEN = "t" * 32
FAST = {"supervision_s": 0.5, "mission_s": 6.0, "pan_settle_s": 0.05, "approach_s": 2.0,
        "lost_s": 0.5, "evidence_dir": None,
        "cabinets": {"rack-02": {"tag_id": 2, "device_id": "pi-02", "host": "pi2", "tcp_ports": [22]}}}


class Car:
    def __init__(self):
        self.moving, self.forwards, self.pan = False, 0, 0

    def stop(self):
        self.moving = False

    def forward(self, p):
        self.moving, self.forwards = True, self.forwards + 1

    def set_dir_servo_angle(self, a):
        pass

    def set_cam_pan_angle(self, a):
        self.pan = a


class Lidar:
    blocked = False

    def get(self, _):
        a = np.radians(np.arange(-30, 31, 2.0))
        return (a, np.full(a.shape, 0.3 if self.blocked else 3.0)), time.time()


class Camera:
    """Tag 2 visible only at pan 20; grows each read while the car drives."""

    def __init__(self, car, grow=0.0):
        self.car, self.size, self.grow = car, 30.0, grow

    def detections(self):
        if self.car.moving:
            self.size += self.grow
        # Seen at pan 20 during the sweep; straight ahead once the approach recentres the camera.
        self.found = getattr(self, "found", False) or self.car.pan == 20
        seen = self.car.pan == 20 or (self.car.pan == 0 and self.found)
        dets = [{"marker_type": "apriltag_36h11", "marker_id": 2, "image_x_norm": -0.1,
                 "size_px": self.size}] if seen else []
        return {"frame_age_s": 0.05, "detections": dets}

    def snapshot(self):
        return b"\xff\xd8jpeg"


def service(tmp_path, grow=0.0, **over):
    car = Car()
    cfg = {**FAST, "evidence_dir": str(tmp_path), **over}
    svc = MissionService(cfg, car, Lidar(), Camera(car, grow),
                         probe=lambda h, p, t: {"name": f"tcp_{p}", "ok": h == "pi2", "latency_ms": 1, "detail": h})
    return svc, car


def call(port, method, path, body=None, token=TOKEN):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def wait_terminal(svc, mid, poll=True, limit=8.0):
    end = time.time() + limit
    while time.time() < end:
        code, v = svc.poll(mid) if poll else (200, svc.missions[mid].view())
        if v["state"] not in ("accepted", "searching", "target_found", "inspecting"):
            return v
        time.sleep(0.05)
    raise AssertionError("mission never finished")


def test_http_contract_no_motion(tmp_path):
    svc, car = service(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc, TOKEN))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    cmd = {"mission_id": "m-1", "action": "inspect_cabinet", "cabinet_id": "rack-02"}
    assert call(port, "POST", "/missions", cmd, token="wrong")[0] == 401
    assert call(port, "POST", "/missions", {**cmd, "cabinet_id": "rack-99"})[0] == 400
    code, v = call(port, "POST", "/missions", cmd)
    assert code == 202 and v["state"] == "accepted"
    assert call(port, "POST", "/missions", {**cmd, "mission_id": "m-2"})[0] == 409  # one at a time
    while v["state"] not in ("completed", "failed", "aborted"):
        time.sleep(0.05)
        v = call(port, "GET", "/missions/m-1")[1]
    r = v["report"]
    assert v["state"] == "completed" and r["status"] == "ok" and r["mission_id"] == "m-1"
    assert r["checks"][0] == {**r["checks"][0], "name": "cabinet_tag", "ok": True}
    assert r["evidence"][0]["sha256"] and (tmp_path / "m-1" / "photo.jpg").exists()
    assert car.forwards == 0 and not car.moving
    assert call(port, "POST", "/missions", cmd)[1]["state"] == "completed"  # idempotent retry
    srv.shutdown()


def test_supervision_loss_aborts_and_stops(tmp_path):
    svc, car = service(tmp_path, motion_enabled=True, approach_s=5.0)  # tag never grows
    svc.submit({"mission_id": "m-3", "action": "inspect_cabinet", "cabinet_id": "rack-02"})
    time.sleep(0.4)
    v = wait_terminal(svc, "m-3", poll=False)  # nobody polls
    assert v == {**v, "state": "aborted", "error": "supervision_lost"}
    assert not car.moving


def test_obstacle_never_drives(tmp_path):
    svc, car = service(tmp_path, grow=5.0, motion_enabled=True)
    svc.lidar.blocked = True
    svc.submit({"mission_id": "m-4", "action": "inspect_cabinet", "cabinet_id": "rack-02"})
    v = wait_terminal(svc, "m-4")
    assert v["state"] == "failed" and car.forwards == 0 and not car.moving


def test_guarded_approach_arrives_and_stops(tmp_path):
    svc, car = service(tmp_path, grow=4.0, motion_enabled=True)
    svc.submit({"mission_id": "m-5", "action": "inspect_cabinet", "cabinet_id": "rack-02"})
    v = wait_terminal(svc, "m-5")
    assert v["state"] == "completed", v
    assert car.forwards > 0 and not car.moving


def test_deadman_stops_stuck_worker(tmp_path):
    svc, car = service(tmp_path)
    svc._drive(0)  # worker drives once then goes silent
    assert car.moving
    time.sleep(0.4)
    assert not car.moving
