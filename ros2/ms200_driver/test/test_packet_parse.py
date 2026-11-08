"""Packet parser tests — no ROS/pyserial needed."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ms200_driver.lidar_serial import (  # noqa: E402
    SerialLidar, _RevolutionAssembler, crc8, parse_packet,
)


def build_packet(start_deg=0.0, end_deg=360.0, dist_mm=1500):
    """Build a syntactically valid 47-byte MS200 packet."""
    p = bytearray(47)
    p[0], p[1] = 0x54, 0x2C
    s = int(start_deg * 100)
    e = int(end_deg * 100)
    p[4], p[5] = s & 0xFF, (s >> 8) & 0xFF
    p[42], p[43] = e & 0xFF, (e >> 8) & 0xFF
    for k in range(12):
        o = 6 + 3 * k
        p[o], p[o + 1] = dist_mm & 0xFF, (dist_mm >> 8) & 0xFF
    p[-1] = crc8(bytes(p[:-1]))
    return bytes(p)


def test_parse_valid_packet():
    pkt = build_packet()
    out = parse_packet(pkt)
    assert out is not None
    start, pts = out
    assert start == 0.0
    assert len(pts) == 12
    ang, dist = pts[0]
    assert dist == 1.5
    assert 0 <= ang < 360


def test_parse_rejects_bad_crc():
    pkt = bytearray(build_packet())
    pkt[-1] ^= 0xFF
    assert parse_packet(bytes(pkt)) is None


def test_parse_rejects_wrong_header():
    pkt = bytearray(build_packet())
    pkt[0] = 0x55
    pkt[-1] = crc8(bytes(pkt[:-1]))
    assert parse_packet(bytes(pkt)) is None


def test_parse_rejects_short():
    assert parse_packet(b"\x54\x2c" + b"\x00" * 10) is None


def test_assembler_emits_revolution():
    asm = _RevolutionAssembler()
    # feed two wraps worth of points (>30 pts/rev to pass emit threshold)
    for deg in list(range(0, 360, 10)) * 2:
        asm.add(float(deg), 2.0)
    asm._emit()  # force flush of second revolution
    scan, stamp = asm.get()
    assert scan is not None
    angles, ranges = scan
    assert len(angles) == len(ranges) > 30
    assert ranges.min() >= 0.05 and ranges.max() <= 12.0
    # angles normalized to [-pi, pi]
    assert angles.min() >= -3.15 and angles.max() <= 3.15


def test_assembler_filters_range():
    asm = _RevolutionAssembler(min_m=0.1, max_m=5.0)
    for deg in range(0, 360, 10):
        asm.add(float(deg), 0.01)   # too close
        asm.add(float(deg), 10.0)   # too far
        asm.add(float(deg), 2.0)    # valid
    asm._emit()
    scan, _ = asm.get()
    assert scan is not None
    _, ranges = scan
    assert (ranges >= 0.1).all() and (ranges <= 5.0).all()


def test_clockwise_mount_offset():
    asm = _RevolutionAssembler(mount_offset_deg=90.0, clockwise=True)
    for deg in range(0, 360, 10):
        asm.add(float(deg), 1.0)
    asm._emit()
    scan, _ = asm.get()
    angles, _ = scan
    # raw 0deg cw -> -0 + 90deg offset = +pi/2
    assert any(abs(a - 1.5707) < 0.01 for a in angles)
