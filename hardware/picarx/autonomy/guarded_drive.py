import argparse
import math
import select
import sys
import termios
import time
import tty

import numpy as np
import yaml
from picarx import Picarx
from lidar import SerialLidar

STOP_M = 0.60          # Measured from the lidar center
HALF_WIDTH_M = 0.16    # Check 16 cm either side of the centerline
SCAN_TIMEOUT = 0.30
KEY_TIMEOUT = 0.35     # Manual movement expires unless W keeps arriving
POWER = 12             # Starting value; motor power is not a speed in m/s


def assess(scan):
    angles, ranges = scan
    valid = np.isfinite(ranges) & (ranges > 0)
    # Require observations across the forward sector.
    for lo, hi in [(-20, -6), (-6, 6), (6, 20)]:
        sector = (angles >= math.radians(lo)) & (angles < math.radians(hi))
        if np.count_nonzero(valid & sector) < 2:
            return "missing forward coverage"

    forward = ranges * np.cos(angles)
    side = ranges * np.sin(angles)
    blocked = valid & (forward > 0) & (forward <= STOP_M) & (
        np.abs(side) <= HALF_WIDTH_M
    )
    if blocked.any():
        return f"obstacle {forward[blocked].min():.2f} m ahead"
    return "clear"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    with open("config.yaml") as file:
        cfg = yaml.safe_load(file)["lidar"]
    lidar = SerialLidar(cfg["port"], cfg["baud"], cfg["mount_offset_deg"],
                        cfg["clockwise"])
    car = Picarx()
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    try:
        car.stop()
        car.set_dir_servo_angle(0)
        tty.setcbreak(fd)
        print("W forward | A/D steer | C center | Space stop | Q quit")
        if args.auto:
            print("AUTO: press G for one straight run, maximum 3 seconds.")
        stamp = 0
        reason = "waiting for lidar"
        previous = None
        deadline = 0
        last_w = float("-inf")
        latched = False
        while True:
            scan, stamp = lidar.get(stamp)
            if scan is not None:
                reason = assess(scan)
            safe = reason if time.time() - stamp <= SCAN_TIMEOUT else "stale scan"
            now = time.monotonic()
            if safe != "clear":
                deadline = 0
                latched = True
            if safe != previous:
                print(safe, flush=True)
                previous = safe

            if select.select([fd], [], [], 0)[0]:
                key = sys.stdin.read(1).lower()
                if key in ("", "q"):
                    break
                if key == " ":
                    deadline = 0
                    latched = True
                elif key == "c":
                    car.set_dir_servo_angle(0)
                elif key in ("a", "d") and not args.auto:
                    car.set_dir_servo_angle(-15 if key == "a" else 15)
                elif key == "w" and not args.auto:
                    # Ignore held-key repeats after a stop until W is released.
                    if safe == "clear" and (not latched or now - last_w > 0.6):
                        deadline = now + KEY_TIMEOUT
                        latched = False
                    last_w = now
                elif key == "g" and args.auto and safe == "clear":
                    car.set_dir_servo_angle(0)
                    deadline = now + 3
            if now < deadline and safe == "clear":
                car.forward(POWER)
            else:
                car.stop()
            time.sleep(0.025)
    finally:
        try:
            car.stop()
            car.set_dir_servo_angle(0)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)


if __name__ == "__main__":
    main()
