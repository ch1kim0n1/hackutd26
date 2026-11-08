import argparse
import json
import math
import os
import select
import signal
import sys
import termios
import time
import tty
from pathlib import Path

import numpy as np
import yaml
from picarx import Picarx

from guarded_drive import POWER, SCAN_TIMEOUT, assess
from lidar import SerialLidar
from turn_test import LEFT_ANGLE, choose

# Experimental starting values, in meters except for the time limits.
HALF_WIDTH = 0.16       # Same lateral margin as guarded_drive.py
LOOKAHEAD = 0.60
TURN_RADIUS = 0.55      # Initial estimate; actual radius is unmeasured
MAX_RUN_S = 1.0
EXIT_S = 0.65           # Short straight finish after passing the box


def points(scan):
    angles, ranges = scan
    return ranges * np.cos(angles), ranges * np.sin(angles)


def arc_clear(scan, sign):
    """Check a band around a short circular arc. Positive sign turns left."""
    x, y = points(scan)
    for distance in np.linspace(0.05, LOOKAHEAD, 16):
        phi = distance / TURN_RADIUS
        cx = TURN_RADIUS * math.sin(phi)
        cy = sign * TURN_RADIUS * (1 - math.cos(phi))
        if np.any((x > 0) & (np.hypot(x - cx, y - cy) <= HALF_WIDTH)):
            return False
    return True


def beside_box(scan, sign):
    # When turning LEFT, the box passes on the RIGHT, and vice versa.
    x, y = points(scan)
    box_side = -sign * y
    side_band = (box_side > HALF_WIDTH) & (box_side < 0.90)
    beside = np.count_nonzero(side_band & (x >= -0.10) & (x <= 0.25)) >= 3
    behind = np.count_nonzero(side_band & (x < -0.10) & (x >= -0.65)) >= 3
    return beside, behind


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive", action="store_true",
                        help="enable movement; default is stationary preview")
    args = parser.parse_args()

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)["lidar"]
    lidar = SerialLidar(cfg["port"], cfg["baud"], cfg["mount_offset_deg"],
                        cfg["clockwise"])

    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    folder = Path("runs") / run_id
    folder.mkdir(parents=True)
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    car = Picarx() if args.drive else None

    def interrupted(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGHUP, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    stamp = 0.0
    scan = None
    state = "IDLE"
    direction = None
    sign = 0
    start = exit_start = 0.0
    seen_side = False
    rear_count = 0
    previous = None

    try:
        if car:
            car.stop()
            car.set_dir_servo_angle(0)
        tty.setcbreak(fd)
        with (folder / "events.jsonl").open("w", buffering=1) as log:
            def record(**data):
                log.write(json.dumps(dict(run_id=run_id, time=time.time(), **data)) + "\n")

            def stop(reason):
                if car:
                    car.stop()
                    car.set_dir_servo_angle(0)
                record(event="stop", reason=reason, power=0, steer_deg=0)
                print(f"STOP: {reason}", flush=True)

            record(event="start", drive=args.drive, angle_unit="rad",
                   range_unit="m", positive_angle="left", power_setting=POWER,
                   left_servo_deg=LEFT_ANGLE, assumed_turn_radius_m=TURN_RADIUS)
            print(f"Recording to {folder}/events.jsonl")
            print("G = start once | Space or Q = stop and exit", flush=True)

            while True:
                key = ""
                if select.select([fd], [], [], 0)[0]:
                    key = os.read(fd, 1).decode(errors="ignore").lower()
                    if key in ("", " ", "q"):
                        stop("operator stop")
                        break

                fresh, stamp = lidar.get(stamp)
                if fresh is not None:
                    scan = fresh
                age = time.time() - stamp
                now = time.monotonic()
                valid = scan is not None and 0 <= age <= SCAN_TIMEOUT
                guard = assess(scan) if valid else "stale scan"

                if fresh is not None:
                    a, r = fresh
                    record(event="scan", scan_time=stamp,
                           angles_rad=a.tolist(), ranges_m=r.tolist())

                if state == "IDLE":
                    choice = choose(scan) if guard == "clear" else "STOP"
                    status = (choice, guard)
                    if status != previous:
                        print(f"Decision: {choice} | guard: {guard}", flush=True)
                        previous = status
                    if key == "g" and choice in ("LEFT", "RIGHT"):
                        direction = choice
                        sign = 1 if direction == "LEFT" else -1
                        if not arc_clear(scan, sign):
                            print("Turn corridor blocked; staying stopped.", flush=True)
                        elif not args.drive:
                            print(f"PREVIEW: would turn {direction}", flush=True)
                            record(event="preview", direction=direction)
                        else:
                            state, start = "TURN", now
                            print(f"TURN {direction}", flush=True)
                    time.sleep(0.01)
                    continue

                if guard != "clear" or now - start >= MAX_RUN_S:
                    stop(guard if guard != "clear" else "run time limit")
                    break
                if fresh is None:
                    time.sleep(0.01)
                    continue

                if state == "TURN":
                    if not arc_clear(scan, sign):
                        stop("turn corridor blocked")
                        break
                    beside, behind = beside_box(scan, sign)
                    seen_side |= beside
                    rear_count = rear_count + 1 if seen_side and behind and not beside else 0
                    if rear_count >= 3:
                        state, exit_start = "EXIT", now
                        print("EXIT: straightening", flush=True)

                if state == "EXIT" and now - exit_start >= EXIT_S:
                    stop("finished straight exit")
                    break

                steer = sign * LEFT_ANGLE if state == "TURN" else 0
                car.set_dir_servo_angle(steer)
                car.forward(POWER)
                record(event="command", state=state, direction=direction,
                       power=POWER, steer_deg=steer, scan_time=stamp)
                time.sleep(0.01)
    finally:
        try:
            if car:
                car.stop()
                car.set_dir_servo_angle(0)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)


if __name__ == "__main__":
    main()
