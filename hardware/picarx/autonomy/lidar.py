"""
2D LiDAR input for the rover.

Every reader yields full revolutions as (angles_rad, ranges_m) numpy arrays in the
ROBOT frame: angle 0 = straight ahead, positive = counter-clockwise (left).

Readers
  SerialLidar  - reads the sensor's serial stream directly (LD06-style packets:
                 0x54 header, 12 points per packet, CRC-8). The Oradar MS200 is
                 commonly run with this packet format at 230400 baud; if you see
                 constant CRC errors, your unit uses a different protocol -> use PipeLidar.
  PipeLidar    - runs the vendor SDK sample (or any program) that prints one point
                 per line as "angle_deg distance_mm" and reads its stdout.
  (sim.SimLidar lives in sim.py)
"""
import math
import subprocess
import threading
import time

import numpy as np


def _crc_table(poly=0x4D):
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = ((c << 1) ^ poly) & 0xFF if c & 0x80 else (c << 1) & 0xFF
        t.append(c)
    return t


_CRC = _crc_table()


def crc8(data):
    c = 0
    for b in data:
        c = _CRC[(c ^ b) & 0xFF]
    return c


class _RevolutionAssembler:
    """Collects points and emits a revolution each time the raw angle wraps past 360."""

    def __init__(self, mount_offset_deg=0.0, clockwise=True, min_m=0.05, max_m=12.0):
        self.off = mount_offset_deg
        self.cw = clockwise
        self.min_m, self.max_m = min_m, max_m
        self.buf_a, self.buf_r = [], []
        self.last_raw = None
        self.latest = None
        self.stamp = 0.0
        self.lock = threading.Lock()

    def add(self, raw_deg, dist_m):
        if self.last_raw is not None and raw_deg + 180 < self.last_raw:   # wrapped
            self._emit()
        self.last_raw = raw_deg
        if self.min_m <= dist_m <= self.max_m:
            a = (-raw_deg if self.cw else raw_deg) + self.off
            self.buf_a.append(math.radians(a))
            self.buf_r.append(dist_m)

    def _emit(self):
        if len(self.buf_a) > 30:
            a = (np.array(self.buf_a) + math.pi) % (2 * math.pi) - math.pi
            with self.lock:
                self.latest = (a, np.array(self.buf_r))
                self.stamp = time.time()
        self.buf_a, self.buf_r = [], []

    def get(self, newer_than=0.0):
        with self.lock:
            if self.latest is None or self.stamp <= newer_than:
                return None, self.stamp
            return self.latest, self.stamp


class SerialLidar:
    PKT = 47

    def __init__(self, port="/dev/ttyUSB0", baud=230400, mount_offset_deg=0.0, clockwise=True):
        import serial  # pyserial
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.asm = _RevolutionAssembler(mount_offset_deg, clockwise)
        self.crc_errors = 0
        self.packets = 0
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        buf = bytearray()
        while True:
            buf += self.ser.read(512)
            while len(buf) >= self.PKT:
                i = buf.find(b"\x54\x2c")
                if i < 0:
                    buf = buf[-1:]
                    break
                if len(buf) - i < self.PKT:
                    buf = buf[i:]
                    break
                p = bytes(buf[i:i + self.PKT])
                buf = buf[i + self.PKT:]
                if crc8(p[:-1]) != p[-1]:
                    self.crc_errors += 1
                    continue
                self.packets += 1
                start = (p[4] | p[5] << 8) / 100.0
                end = (p[42] | p[43] << 8) / 100.0
                span = (end - start) % 360.0
                for k in range(12):
                    o = 6 + 3 * k
                    d = (p[o] | p[o + 1] << 8) / 1000.0
                    self.asm.add((start + span * k / 11.0) % 360.0, d)

    def get(self, newer_than=0.0):
        return self.asm.get(newer_than)


class PipeLidar:
    """cmd prints lines like '123.45 1530' (degrees, millimetres)."""

    def __init__(self, cmd, mount_offset_deg=0.0, clockwise=True):
        self.proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.asm = _RevolutionAssembler(mount_offset_deg, clockwise)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        for line in self.proc.stdout:
            parts = line.replace(",", " ").split()
            if len(parts) < 2:
                continue
            try:
                self.asm.add(float(parts[0]) % 360.0, float(parts[1]) / 1000.0)
            except ValueError:
                continue

    def get(self, newer_than=0.0):
        return self.asm.get(newer_than)


def sector_min(angles, ranges, lo_deg, hi_deg, default=12.0):
    """Closest return between lo and hi degrees (robot frame, CCW positive)."""
    lo, hi = math.radians(lo_deg), math.radians(hi_deg)
    m = (angles >= lo) & (angles <= hi)
    return float(ranges[m].min()) if m.any() else default
