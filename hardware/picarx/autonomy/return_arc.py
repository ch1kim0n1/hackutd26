import time
import yaml
import numpy as np
from picarx import Picarx
from lidar import SerialLidar
from guarded_drive import assess, POWER, SCAN_TIMEOUT

RIGHT_ANGLE = 15       # Same command as D in guarded_drive.py
TURN_SECONDS = 1.75

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)["lidar"]

lidar = SerialLidar(cfg["port"], cfg["baud"], cfg["mount_offset_deg"],
                    cfg["clockwise"])
car = Picarx()

try:
    car.stop()
    car.set_dir_servo_angle(0)
    input("Press Enter for one right arc. Ctrl+C cancels. ")
    car.set_dir_servo_angle(RIGHT_ANGLE)
    time.sleep(0.2)    # Let the wheels turn before starting the motors

    stamp = time.time()  # Require a new scan after steering
    wait_until = time.monotonic() + SCAN_TIMEOUT
    started = None

    while True:
        now = time.monotonic()
        if started is not None and now - started >= TURN_SECONDS:
            reason = "timed arc complete"
            break

        scan, stamp = lidar.get(stamp)
        if scan is None:
            if now >= wait_until:
                reason = "stale lidar scan"
                break
            time.sleep(0.01)
            continue

        status = assess(scan)
        if status != "clear":
            reason = status
            break

        # Also check the front-right sector toward which we're turning.
        angles, ranges = scan
        right = ranges[(angles >= np.radians(-60)) & (angles < 0)]
        if len(right) < 3 or np.min(right) <= 0.60:
            reason = "front-right sector blocked or missing"
            break

        wait_until = now + SCAN_TIMEOUT
        if started is None:
            car.forward(POWER)
            started = time.monotonic()

    car.stop()
    elapsed = 0.0 if started is None else time.monotonic() - started
    print(f"Stopped: {reason}. Forward command lasted {elapsed:.2f} s.")
finally:
    car.stop()
    car.set_dir_servo_angle(0)
