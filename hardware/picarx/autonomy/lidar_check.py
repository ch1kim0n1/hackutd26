#!/usr/bin/env python3
"""
Check the LiDAR before letting the rover drive.
  python3 lidar_check.py            # uses config.yaml lidar settings
Prints scans/s, points per scan, CRC errors (serial mode) and the closest object's
angle. Put a box straight in front of the car: the angle should read about 0 deg.
If it reads e.g. 90, set lidar.mount_offset_deg: -90 in config.yaml. If moving the box
to the car's LEFT makes the angle go negative, flip lidar.clockwise.
"""
import math
import os
import time

import numpy as np
import yaml

from lidar import PipeLidar, SerialLidar

cfg = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")))["lidar"]
lid = SerialLidar(cfg["port"], cfg["baud"], cfg["mount_offset_deg"], cfg["clockwise"]) if cfg["mode"] == "serial" \
    else PipeLidar(cfg["pipe_cmd"], cfg["mount_offset_deg"], cfg["clockwise"])
stamp, count, t0 = 0.0, 0, time.time()
while True:
    scan, stamp_new = lid.get(stamp)
    if scan is None:
        time.sleep(0.02)
        if time.time() - t0 > 5 and count == 0:
            extra = f" crc_errors={lid.crc_errors} packets={lid.packets}" if hasattr(lid, "crc_errors") else ""
            print("No full scans yet." + extra + "  Many CRC errors -> protocol differs, use pipe mode.")
            t0 = time.time()
        continue
    stamp = stamp_new
    count += 1
    a, r = scan
    i = int(np.argmin(r))
    rate = count / (time.time() - t0 + 1e-9)
    front = r[np.abs(a) < math.radians(10)]
    print(f"{rate:4.1f} scans/s  {len(a):4d} pts  closest {r[i]:.2f} m at {math.degrees(a[i]):6.1f} deg  "
          f"front(+-10deg) {front.min() if len(front) else float('nan'):.2f} m")
