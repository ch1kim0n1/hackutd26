import argparse
import time

import numpy as np
import yaml
from picarx import Picarx
from lidar import SerialLidar
from guarded_drive import assess, POWER, SCAN_TIMEOUT

LEFT_ANGLE = -15  # Verify on your rover before the floor test.


def choose(scan):
    angles, ranges = scan
    degrees = np.degrees(angles)

    def nearest(lo, hi):
        points = ranges[(degrees >= lo) & (degrees < hi)]
        return float(points.min()) if len(points) >= 3 else None

    left = nearest(15, 55)
    front = nearest(-15, 15)
    right = nearest(-55, -15)
    if None in (left, front, right):
        return "STOP"
    if not 0.60 <= front <= 1.00:
        return "STOP"
    if max(left, right) < 1.00 or abs(left - right) < 0.15:
        return "STOP"
    return "LEFT" if left > right else "RIGHT"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive", action="store_true")
    args = parser.parse_args()

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)["lidar"]
    lidar = SerialLidar(cfg["port"], cfg["baud"], cfg["mount_offset_deg"],
                        cfg["clockwise"])
    car = Picarx()
    try:
        car.stop()
        car.set_dir_servo_angle(0)
        input("Press Enter for one test. Ctrl+C cancels. ")
        # Require a scan acquired after Enter.
        stamp = time.time()
        start = time.monotonic()
        direction = None
        while time.monotonic() - start < SCAN_TIMEOUT:
            scan, stamp = lidar.get(stamp)
            if scan is None:
                time.sleep(0.01)
                continue
            status = assess(scan)
            direction = choose(scan) if status == "clear" else "STOP"
            break

        if direction not in ("LEFT", "RIGHT"):
            print("STOP: no fresh, clear turn available.")
            return

        print(f"Steering {direction}", flush=True)
        car.set_dir_servo_angle(LEFT_ANGLE if direction == "LEFT" else -LEFT_ANGLE)
        if not args.drive:
            time.sleep(2)
            return

        # Recheck after steering. Start motion only on a new, usable scan.
        deadline = time.monotonic() + 0.6
        while time.monotonic() < deadline:
            scan, stamp = lidar.get(stamp)
            if time.time() - stamp > SCAN_TIMEOUT:
                print("STOP: stale scan")
                break
            if scan is not None:
                status = assess(scan)
                if status != "clear" or choose(scan) != direction:
                    print(f"STOP: {status}; turn no longer confirmed")
                    break
                car.forward(POWER)
            time.sleep(0.01)
    finally:
        car.stop()
        car.set_dir_servo_angle(0)


if __name__ == "__main__":
    main()
