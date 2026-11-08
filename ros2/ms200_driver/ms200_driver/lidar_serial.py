"""ORADAR MS200 serial reader — vendored from autonomy/lidar.py.

LD06-style packets: 0x54 0x2C header, 47 bytes, 12 points/packet,
CRC-8 (poly 0x4D). 230400 baud UART via USB-UART adapter.
Revolution assembler emits (angles_rad, ranges_m) in robot frame:
angle 0 = straight ahead, positive = counter-clockwise.
"""
import math
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


def parse_packet(pkt: bytes):
    """47-byte MS200/LD06 packet -> (start_deg, [(angle_deg, dist_m)x12]).
    Returns None on bad length or CRC mismatch."""
    if len(pkt) != 47 or pkt[0] != 0x54 or pkt[1] != 0x2C:
        return None
    if crc8(pkt[:-1]) != pkt[-1]:
        return None
    start = (pkt[4] | pkt[5] << 8) / 100.0
    end = (pkt[42] | pkt[43] << 8) / 100.0
    span = (end - start) % 360.0
    pts = []
    for k in range(12):
        o = 6 + 3 * k
        d = (pkt[o] | pkt[o + 1] << 8) / 1000.0
        pts.append(((start + span * k / 11.0) % 360.0, d))
    return start, pts


class _RevolutionAssembler:
    def __init__(self, mount_offset_deg=0.0, clockwise=True,
                 min_m=0.05, max_m=12.0):
        self.off = mount_offset_deg
        self.cw = clockwise
        self.min_m, self.max_m = min_m, max_m
        self.buf_a, self.buf_r = [], []
        self.last_raw = None
        self.latest = None
        self.stamp = 0.0
        self.lock = threading.Lock()

    def add(self, raw_deg, dist_m):
        if self.last_raw is not None and raw_deg + 180 < self.last_raw:
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

    def __init__(self, port="/dev/ttyUSB0", baud=230400,
                 mount_offset_deg=0.0, clockwise=True):
        import serial  # pyserial — present on the robot/PC image
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
                pkt = bytes(buf[i:i + self.PKT])
                buf = buf[i + self.PKT:]
                parsed = parse_packet(pkt)
                if parsed is None:
                    self.crc_errors += 1
                    continue
                self.packets += 1
                start, pts = parsed
                for ang, d in pts:
                    self.asm.add(ang, d)

    def get(self, newer_than=0.0):
        return self.asm.get(newer_than)
