import math
import time
from picarx import Picarx

PAN = 15      # Degrees to either side of center
TILT = 8      # Start smaller on the axis carrying the camera's weight
SECONDS = 2.0 # Time for each move
HZ = 25

car = Picarx()
car.stop()
pan = tilt = 0.0

def move(target_pan, target_tilt):
    global pan, tilt
    start_pan, start_tilt = pan, tilt
    steps = round(SECONDS * HZ)
    start = time.monotonic()

    for i in range(1, steps + 1):
        deadline = start + i * SECONDS / steps
        time.sleep(max(0.0, deadline - time.monotonic()))

        # Ease in and out so the mount starts and ends each move gently.
        fraction = (1 - math.cos(math.pi * i / steps)) / 2
        pan = start_pan + (target_pan - start_pan) * fraction
        tilt = start_tilt + (target_tilt - start_tilt) * fraction
        car.set_cam_pan_angle(pan)
        car.set_cam_tilt_angle(tilt)

def phase(label, positions):
    input(f"\n{label}: press Enter to start, or Ctrl+C to stop. ")
    for target_pan, target_tilt in positions:
        print(f"Pan {target_pan:+}°, tilt {target_tilt:+}°", flush=True)
        move(target_pan, target_tilt)
        time.sleep(1.0)  # Watch for droop or shaking while holding position.

try:
    car.set_cam_pan_angle(0)
    car.set_cam_tilt_angle(0)
    phase("Tilt only", [(0, TILT), (0, -TILT), (0, 0)])
    phase("Pan only", [(PAN, 0), (-PAN, 0), (0, 0)])
    phase("Combined", [(PAN, TILT), (-PAN, -TILT), (0, 0)])
    print("Finished at center.")
except KeyboardInterrupt:
    print("\nSweep stopped at its current position.")
finally:
    car.stop()
