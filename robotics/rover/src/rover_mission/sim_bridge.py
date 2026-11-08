"""Sim-to-twin bridge (issue #116).

Tails the JSONL pose stream written by ``autonomy/run.py --sim
--pose-stream FILE`` and republishes each fix as rover-shape mission
telemetry on the device ACL topic (``sentinel/v1/<device>/telemetry``).
The existing gateway ``normalizeTelemetry`` -> ``ingestObservation`` path
carries it to ``observationFeed``; Phantom Command renders the pose on the
digital twin.

Pose is emitted in the common telemetry pose shape ``{x, y, heading_rad,
unit: 'm', frame: 'autonomy_map'}`` — the autonomy sim world frame, NOT the
surveyed floorplan. The dashboard applies the documented sim-room ->
facility transform; nothing is re-fabricated here. ``provenance`` stays
``SIM`` end to end.

Reconnect/resync: paho-mqtt reconnects the broker link on its own; this
bridge detects stream truncation/rotation, rescans, and dedupes on fix
content so a rescan never double-publishes. The gateway assigns the
per-device monotonic seq and synthesizes ``event_id``, so SpacetimeDB
replay protection still applies downstream.

Map/scan occupancy is intentionally NOT bridged: the autonomy grid is a
local log-odds map with no surveyed-frame registration yet — see
docs/14-ROVER-MISSION-CONTRACT.md (pose frames never comparable across
``autonomy_map``/``surveyed_floorplan``).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import OrderedDict
from typing import Iterator, Optional, Protocol

from .telemetry import publisher_from_env

POSE_STREAM_PROVENANCE = "SIM"
DEFAULT_DEVICE_ID = "rover-01"
DEFAULT_ZONE_ID = "lab-floor"
DEFAULT_MISSION_ID = "sim-patrol"
SEEN_CAP = 512


class Publisher(Protocol):
    def publish(self, event: dict) -> None: ...


def _utc_now_ms() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _fix_observed_at(fix: dict) -> str:
    """Deterministic observed_at from the fix's wall-clock ``ts`` (unix s,
    written by run.py). Stable across bridge restarts -> the gateway's
    synthesized event_id dedupes republishes instead of duplicating rows.
    Falls back to publish time for streams without ``ts``."""
    ts = fix.get("ts")
    if isinstance(ts, (int, float)):
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts, timezone.utc).isoformat(
            timespec="milliseconds").replace("+00:00", "Z")
    return _utc_now_ms()


def _fix_key(fix: dict) -> tuple:
    return (fix.get("t"), fix.get("x"), fix.get("y"), fix.get("theta"), fix.get("mode"))


def fix_to_event(
    fix: dict,
    *,
    device_id: str = DEFAULT_DEVICE_ID,
    zone_id: str = DEFAULT_ZONE_ID,
    mission_id: str = DEFAULT_MISSION_ID,
    observed_at: Optional[str] = None,
) -> dict:
    """One pose-stream fix -> rover-shape telemetry event (gateway contract)."""
    # The gateway synthesizes event_id as
    # device:mission:command:event:observed_ms. observed_at comes from the
    # fix's own capture timestamp (stable across republishes -> replay-safe
    # dedupe); command_id carries the sim fix index so fixes emitted in the
    # same millisecond still get distinct event_ids.
    observed = observed_at or _fix_observed_at(fix)
    pose = {
        "x": fix["x"],
        "y": fix["y"],
        "heading_rad": fix["theta"],
        "unit": "m",
        "frame": "autonomy_map",
        "source": "autonomy_sim",
    }
    if fix.get("confidence") is not None:
        pose["confidence"] = fix["confidence"]
    return {
        "event": "pose",
        "schema_version": 1,
        "device_id": device_id,
        "mission_id": mission_id,
        "command_id": f"sim-stream:t{fix.get('t')}",
        "type": "patrol",
        "state": "navigating",
        "zone_id": zone_id,
        "observed_at": observed,
        "pose_confidence": fix.get("pose_confidence"),
        "reason": f"autonomy sim mode={fix.get('mode', 'unknown')}",
        "provenance": POSE_STREAM_PROVENANCE,
        "sim_t": fix.get("t"),
        "mode": fix.get("mode"),
        "pose": pose,
    }


def parse_fix(line: str) -> Optional[dict]:
    """JSONL line -> fix dict, or None for blank/malformed lines."""
    line = line.strip()
    if not line:
        return None
    try:
        fix = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(fix, dict):
        return None
    for k in ("x", "y", "theta"):
        if not isinstance(fix.get(k), (int, float)):
            return None
    return fix


def iter_stream(path: str, offset: int) -> Iterator[tuple[int, str]]:
    """Yield (new_offset, complete_line) for complete newline-terminated
    lines appended since ``offset``. A shrinking file means rotation —
    restart at 0 so no fixes are lost."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size < offset:
        offset = 0  # truncated/rotated: rescan from the top
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
        end = data.rfind(b"\n")
        if end < 0:
            return  # no complete line yet
        consumed = data[: end + 1]
        new_offset = offset + len(consumed)
        for raw in consumed.splitlines():
            yield new_offset, raw.decode("utf-8", errors="replace")


class SimBridge:
    """Follow a pose stream and publish each new fix once."""

    def __init__(
        self,
        publisher: Publisher,
        *,
        device_id: str = DEFAULT_DEVICE_ID,
        zone_id: str = DEFAULT_ZONE_ID,
        mission_id: str = DEFAULT_MISSION_ID,
    ) -> None:
        self.publisher = publisher
        self.device_id = device_id
        self.zone_id = zone_id
        self.mission_id = mission_id
        self.offset = 0
        self.published = 0
        self._seen: "OrderedDict[tuple, None]" = OrderedDict()

    def _fresh(self, fix: dict) -> bool:
        key = _fix_key(fix)
        if key in self._seen:
            return False
        self._seen[key] = None
        self._seen.move_to_end(key)
        while len(self._seen) > SEEN_CAP:
            self._seen.popitem(last=False)
        return True

    def poll_once(self, path: str) -> int:
        """Publish all complete new lines; returns count published."""
        n = 0
        for new_offset, line in iter_stream(path, self.offset):
            self.offset = new_offset
            fix = parse_fix(line)
            if fix is None or not self._fresh(fix):
                continue
            try:
                self.publisher.publish(
                    fix_to_event(
                        fix,
                        device_id=self.device_id,
                        zone_id=self.zone_id,
                        mission_id=self.mission_id,
                    )
                )
            except Exception as exc:  # telemetry loss must not kill the bridge
                print(f"[sim-bridge] publish failed: {exc}", flush=True)
                continue
            self.published += 1
            n += 1
        return n

    def follow(self, path: str, poll_s: float = 0.25) -> None:
        print(f"[sim-bridge] tailing {path} -> {self.device_id} "
              f"(zone={self.zone_id}, mission={self.mission_id})", flush=True)
        while True:
            self.poll_once(path)
            time.sleep(poll_s)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="autonomy sim -> twin telemetry bridge")
    ap.add_argument("--stream", required=True, help="pose JSONL from run.py --pose-stream")
    ap.add_argument("--device", default=os.environ.get("ROVER_DEVICE_ID", DEFAULT_DEVICE_ID))
    ap.add_argument("--zone", default=os.environ.get("ROVER_ZONE_ID", DEFAULT_ZONE_ID))
    ap.add_argument("--mission-id", default=DEFAULT_MISSION_ID)
    ap.add_argument("--poll-s", type=float, default=0.25)
    args = ap.parse_args(argv)

    pub = publisher_from_env()
    bridge = SimBridge(pub, device_id=args.device, zone_id=args.zone, mission_id=args.mission_id)
    bridge.follow(args.stream, poll_s=args.poll_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
