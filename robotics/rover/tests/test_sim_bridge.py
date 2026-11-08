"""Sim-to-twin bridge tests (issue #116): pose-stream -> rover-shape
events, tail/dedupe/resync semantics, publisher failure tolerance."""
import json

import pytest

from rover_mission.sim_bridge import (
    SimBridge, fix_to_event, iter_stream, parse_fix,
)


class Recorder:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def _fix(t=1.0, x=0.5, y=-0.25, theta=0.3, mode="patrol"):
    return {"t": t, "x": x, "y": y, "theta": theta, "mode": mode,
            "provenance": "SIM"}


def _write(path, fixes):
    with open(path, "w") as fh:
        for f in fixes:
            fh.write(json.dumps(f) + "\n")


# ---------------- event shape ----------------

def test_fix_to_event_rover_shape():
    ev = fix_to_event(_fix(), device_id="rover-01", zone_id="lab-floor",
                      mission_id="sim-patrol", observed_at="2026-01-01T00:00:00Z")
    # Fields the gateway normalizeTelemetry rover-shape path requires.
    assert ev["schema_version"] == 1
    assert ev["mission_id"] == "sim-patrol"
    assert isinstance(ev["state"], str) and ev["state"]
    assert isinstance(ev["event"], str) and ev["event"]
    assert ev["zone_id"] == "lab-floor"
    assert ev["observed_at"] == "2026-01-01T00:00:00Z"
    assert ev["device_id"] == "rover-01"
    # Pose stays in the autonomy sim frame — never re-labelled surveyed.
    pose = ev["pose"]
    assert pose["x"] == 0.5 and pose["y"] == -0.25
    assert pose["heading_rad"] == 0.3
    assert pose["unit"] == "m" and pose["frame"] == "autonomy_map"
    assert pose["source"] == "autonomy_sim"
    assert ev["provenance"] == "SIM"


def test_fix_to_event_observed_at_deterministic_from_ts():
    fix = {**_fix(t=3.4), "ts": 1_700_000_000.123}
    a = fix_to_event(fix)
    b = fix_to_event(fix)
    # Stable across republishes -> gateway event_id dedupes, no dup rows.
    assert a["observed_at"] == b["observed_at"] == "2023-11-14T22:13:20.123Z"
    assert a["command_id"] == "sim-stream:t3.4"
    # Stream without ts falls back to publish time (still valid ISO).
    c = fix_to_event(_fix(t=9.9))
    assert c["observed_at"].endswith("Z") and "T" in c["observed_at"]


def test_fix_to_event_optional_confidence():
    ev = fix_to_event({**_fix(), "confidence": 0.7})
    assert ev["pose"]["confidence"] == 0.7
    ev2 = fix_to_event(_fix())
    assert "confidence" not in ev2["pose"]


# ---------------- stream parsing ----------------

def test_parse_fix_valid_and_invalid():
    assert parse_fix('{"x":1,"y":2,"theta":0.5}') == {"x": 1, "y": 2, "theta": 0.5}
    assert parse_fix("") is None
    assert parse_fix("not json") is None
    assert parse_fix('{"x":"a","y":2,"theta":0}') is None
    assert parse_fix("[1,2,3]") is None


def test_iter_stream_offset_and_partial(tmp_path):
    p = tmp_path / "pose.jsonl"
    p.write_text('{"x":0,"y":0,"theta":0}\n{"x":1,"y":1,"theta":0.1}\n')
    size = p.stat().st_size
    lines = list(iter_stream(str(p), 0))
    assert len(lines) == 2 and lines[-1][0] == size
    # No new complete lines -> nothing.
    assert list(iter_stream(str(p), size)) == []
    # Partial trailing line is not emitted until terminated.
    with open(p, "a") as fh:
        fh.write('{"x":2,"y":2,"theta":0.2')   # no newline yet
    assert list(iter_stream(str(p), size)) == []
    with open(p, "a") as fh:
        fh.write("}\n")
    got = list(iter_stream(str(p), size))
    assert len(got) == 1 and '"x":2' in got[0][1]


def test_iter_stream_rotation_rescans(tmp_path):
    p = tmp_path / "pose.jsonl"
    _write(p, [_fix(t=1), _fix(t=2)])
    size = p.stat().st_size
    # Rotate: replace with a shorter file -> offset resets, no loss.
    _write(p, [_fix(t=9)])
    got = [line for _, line in iter_stream(str(p), size)]
    assert len(got) == 1 and '"t": 9' in got[0]


# ---------------- bridge behaviour ----------------

def test_bridge_publishes_new_fixes_once(tmp_path):
    p = tmp_path / "pose.jsonl"
    _write(p, [_fix(t=1), _fix(t=2), _fix(t=3)])
    rec = Recorder()
    bridge = SimBridge(rec, device_id="rover-01")
    assert bridge.poll_once(str(p)) == 3
    assert bridge.published == 3
    assert rec.events[0]["pose"]["frame"] == "autonomy_map"
    # Re-poll: nothing new.
    assert bridge.poll_once(str(p)) == 0
    assert len(rec.events) == 3


def test_bridge_incremental_and_dedupe(tmp_path):
    p = tmp_path / "pose.jsonl"
    _write(p, [_fix(t=1)])
    rec = Recorder()
    bridge = SimBridge(rec)
    assert bridge.poll_once(str(p)) == 1
    with open(p, "a") as fh:
        fh.write(json.dumps(_fix(t=2)) + "\n")
        fh.write(json.dumps(_fix(t=2)) + "\n")  # duplicate line
    assert bridge.poll_once(str(p)) == 1
    assert len(rec.events) == 2


def test_bridge_survives_rotation_without_duplicates(tmp_path):
    p = tmp_path / "pose.jsonl"
    _write(p, [_fix(t=1), _fix(t=2)])
    rec = Recorder()
    bridge = SimBridge(rec)
    bridge.poll_once(str(p))
    # Sim restarts and rewrites the same fixes plus a new one.
    _write(p, [_fix(t=1), _fix(t=2), _fix(t=3)])
    assert bridge.poll_once(str(p)) == 1  # only t=3 is fresh
    assert len(rec.events) == 3


def test_bridge_missing_file_waits(tmp_path):
    rec = Recorder()
    bridge = SimBridge(rec)
    assert bridge.poll_once(str(tmp_path / "nope.jsonl")) == 0


def test_bridge_publish_failure_continues(tmp_path):
    class BadPublisher:
        def __init__(self):
            self.calls = 0

        def publish(self, event):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("broker down")

    p = tmp_path / "pose.jsonl"
    _write(p, [_fix(t=1), _fix(t=2)])
    pub = BadPublisher()
    bridge = SimBridge(pub)
    assert bridge.poll_once(str(p)) == 1  # second fix still published
    assert pub.calls == 2
    assert bridge.published == 1


def test_bridge_malformed_lines_skipped(tmp_path):
    p = tmp_path / "pose.jsonl"
    p.write_text("garbage\n" + json.dumps(_fix(t=1)) + "\n{\"x\":\"bad\"}\n")
    rec = Recorder()
    bridge = SimBridge(rec)
    assert bridge.poll_once(str(p)) == 1
