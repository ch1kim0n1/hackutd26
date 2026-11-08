"""Autonomy-side rover mission contract — sentinel.rover.* v1 port.

Issue #115 / docs/14. Self-contained port of ``rover_mission.common`` for the
``autonomy/`` stack: this directory deploys to the Pi as flat scripts with
minimal deps and cannot import the ``rover_mission`` package, so the mapping
tables and validators are duplicated here ON PURPOSE. ``rover_mission``'s
``tests/test_common_contract.py`` loads this file and asserts parity — drift
between the two implementations fails CI.

autonomy/ is onboard local control: it has no mission queue and never accepts
remote actuator commands. A *directive* is an advisory behavior request
(PATROL/CHECKPOINT/RETURN_HOME/STOP) that a runtime binding may use to scope
waypoints or trigger scan checkpoints; E-stop, watchdogs and the local
planner always remain authoritative (docs/03, docs/14 §7).
"""

from __future__ import annotations

import time
from typing import Mapping, Optional

SCHEMA_VERSION = 1

CONTRACT_MISSION = "sentinel.rover.mission"
CONTRACT_TELEMETRY = "sentinel.rover.telemetry"
CONTRACT_DIRECTIVE = "sentinel.rover.autonomy_directive"

PROVENANCE_VALUES = frozenset({"DEMO", "REPLAY", "LIVE"})

COMMON_MISSION_TYPES = frozenset({
    "inspect_zone", "patrol", "capture_photo", "return_home", "hold",
    "wireless_rescan",
})
MODULE_MISSION_TYPES = frozenset({
    "inspect_zone", "patrol", "capture_photo", "return_home", "hold",
})

TYPE_TO_ROVER = {
    "inspect_zone": "inspect_zone",
    "patrol": "patrol_route",
    "capture_photo": "capture_photo",
    "return_home": "return_home",
    "hold": "stop",
    "wireless_rescan": "wireless_rescan",
}
TYPE_FROM_ROVER = {v: k for k, v in TYPE_TO_ROVER.items()}

MISSION_REQUIRED_FIELDS = {
    "inspect_zone": ("zone_id", "waypoint_id"),
    "patrol": (),
    "capture_photo": (),
    "return_home": (),
    "hold": (),
    "wireless_rescan": ("zone_id",),
}
MISSION_ANY_OF_FIELDS = {
    "patrol": (("waypoint_id", "route_id"),),
}
MODULE_REQUIRED_FIELDS = {
    "inspect_zone": ("zone_id", "waypoint_id"),
    "patrol": ("zone_id", "waypoint_id"),
    "capture_photo": ("zone_id", "waypoint_id"),
    "return_home": ("zone_id", "waypoint_id"),
    "hold": ("zone_id", "waypoint_id"),
}
MODULE_SPEED_MIN_EXCLUSIVE = 0.05
MODULE_SPEED_MAX = 0.5

ROVER_STATES = frozenset({
    "queued", "accepted", "navigating", "scanning",
    "completed", "failed", "aborted", "timed_out",
})
COMMON_STATES = frozenset({
    "proposed", "approved", "dispatched", "queued",
    "accepted", "navigating", "scanning",
    "completed", "failed", "aborted", "timed_out",
    "expired", "cancelled",
})

POSE_UNITS = frozenset({"mm", "m"})
AUTONOMY_POSE_UNIT = "m"
AUTONOMY_POSE_FRAME = "autonomy_map"

# autonomy directive behaviors (brain.py mode vocabulary + advisory stop)
DIRECTIVE_BEHAVIORS = frozenset({
    "PATROL", "CHECKPOINT", "RETURN_HOME", "STOP",
    "EXPLORE", "COVER", "WALL_FOLLOW",
})

# common type -> directive behavior. capture_photo/inspect_zone degrade to
# waypoint-scoped PATROL/CHECKPOINT — autonomy has no camera and checkpoints
# are its only evidence-adjacent behavior (docs/14 §6).
TYPE_TO_BEHAVIOR = {
    "patrol": "PATROL",
    "inspect_zone": "PATROL",
    "capture_photo": "CHECKPOINT",
    "wireless_rescan": "CHECKPOINT",
    "return_home": "RETURN_HOME",
    "hold": "STOP",
}
BEHAVIOR_TO_TYPE = {
    "PATROL": "patrol",
    "CHECKPOINT": "inspect_zone",
    "RETURN_HOME": "return_home",
    "STOP": "hold",
    "EXPLORE": None,   # autonomy-native behaviors have no mission type
    "COVER": None,
    "WALL_FOLLOW": None,
}


def _is_str(v) -> bool:
    return isinstance(v, str) and len(v) > 0


def _is_ascii(v) -> bool:
    return isinstance(v, str) and all(ord(c) < 128 for c in v)


def _check_strings_ascii(m: Mapping) -> Optional[str]:
    for k, v in m.items():
        if isinstance(v, str) and not _is_ascii(v):
            return f"non-ascii field {k}"
    return None


def _parse_iso(s: str) -> float:
    from datetime import datetime, timezone
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    return datetime.fromisoformat(t).astimezone(timezone.utc).timestamp()


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def validate_common_mission(m) -> tuple[bool, str]:
    """Mirror of rover_mission.common.validate_common_mission (parity-tested)."""
    if not isinstance(m, Mapping):
        return False, "not an object"
    if m.get("contract") != CONTRACT_MISSION:
        return False, "bad_contract"
    if m.get("schema_version") != SCHEMA_VERSION:
        return False, "bad_schema_version"
    for f in ("mission_id", "command_id", "device_id", "type"):
        if not _is_str(m.get(f)):
            return False, f"missing_{f}"
    bad = _check_strings_ascii(m)
    if bad:
        return False, bad
    mtype = m["type"]
    if mtype not in COMMON_MISSION_TYPES:
        return False, "unknown_type"
    for f in MISSION_REQUIRED_FIELDS[mtype]:
        if not _is_str(m.get(f)):
            return False, f"missing_{f}"
    for group in MISSION_ANY_OF_FIELDS.get(mtype, ()):
        if not any(_is_str(m.get(f)) for f in group):
            return False, "missing_" + "|".join(group)
    speed = m.get("max_speed_mps")
    if speed is not None and (
            not isinstance(speed, (int, float)) or isinstance(speed, bool)
            or float(speed) <= 0):
        return False, "bad_max_speed_mps"
    expires = m.get("expires_at")
    if not _is_str(expires):
        return False, "missing_expires_at"
    try:
        _parse_iso(expires)
    except (ValueError, TypeError):
        return False, "bad_expires_at"
    return True, ""


def _valid_pose(p) -> bool:
    return (
        isinstance(p, Mapping)
        and isinstance(p.get("x"), (int, float))
        and isinstance(p.get("y"), (int, float))
        and isinstance(p.get("heading_rad"), (int, float))
        and p.get("unit") in POSE_UNITS
        and _is_str(p.get("frame"))
    )


def validate_common_telemetry(t) -> tuple[bool, str]:
    """Mirror of rover_mission.common.validate_common_telemetry."""
    if not isinstance(t, Mapping):
        return False, "not an object"
    if t.get("contract") != CONTRACT_TELEMETRY:
        return False, "bad_contract"
    if t.get("schema_version") != SCHEMA_VERSION:
        return False, "bad_schema_version"
    if not _is_str(t.get("event")) or not _is_str(t.get("device_id")):
        return False, "missing_event_or_device"
    if t.get("provenance") not in PROVENANCE_VALUES:
        return False, "bad_provenance"
    if not _is_str(t.get("observed_at")):
        return False, "missing_observed_at"
    try:
        _parse_iso(t["observed_at"])
    except (ValueError, TypeError):
        return False, "bad_observed_at"
    for f in ("mission_id", "command_id", "zone_id", "waypoint_id"):
        if t.get(f) is not None and not _is_str(t[f]):
            return False, f"bad_{f}"
    if t.get("type") is not None and t["type"] not in COMMON_MISSION_TYPES:
        return False, "unknown_type"
    if t.get("state") is not None and t["state"] not in COMMON_STATES:
        return False, "unknown_state"
    if t.get("pose") is not None and not _valid_pose(t["pose"]):
        return False, "bad_pose"
    if t.get("data") is not None and not isinstance(t["data"], Mapping):
        return False, "bad_data"
    return True, ""


def pose_from_autonomy(pose, *, source: str = "odometry+scan_match") -> dict:
    x, y, th = pose[0], pose[1], pose[2]
    return {
        "x": x, "y": y, "heading_rad": th,
        "unit": AUTONOMY_POSE_UNIT, "frame": AUTONOMY_POSE_FRAME,
        "source": source,
    }


# ---------------------------------------------------------------------------
# Mission <-> directive mapping
# ---------------------------------------------------------------------------

def _resolve_waypoints(common: Mapping, waypoint_table: Optional[Mapping]) -> list:
    """Resolve common waypoint/route refs to autonomy config waypoints.

    ``waypoint_table`` maps common waypoint_id (or route_ref for patrol) to
    autonomy config entries {name, xy:[x,y]}. Entries may also be keyed by
    route_ref for patrol missions. Unresolvable refs stay as refs — the
    binding layer decides whether to fail closed.
    """
    if not waypoint_table:
        return []
    refs = []
    if common.get("waypoint_id"):
        refs.append(common["waypoint_id"])
    if common.get("route_id"):
        refs.append(common["route_id"])
    out = []
    for ref in refs:
        wp = waypoint_table.get(ref)
        if isinstance(wp, Mapping) and "xy" in wp:
            out.append({"ref": ref, "name": wp.get("name", ref),
                        "xy": list(wp["xy"])})
    return out


def common_to_directive(common, *, waypoint_table: Optional[Mapping] = None,
                        now: Optional[float] = None) -> Optional[dict]:
    """Common mission -> autonomy behavior directive (advisory, non-binding).

    ``timeout_s`` derives from expires_at so a runtime binding can bound the
    behavior; autonomy's own watchdog/E-stop are unaffected.
    """
    ok, _ = validate_common_mission(common)
    if not ok:
        return None
    mtype = common["type"]
    behavior = TYPE_TO_BEHAVIOR[mtype]
    now = time.time() if now is None else now
    try:
        timeout_s = max(0.0, _parse_iso(common["expires_at"]) - now)
    except (ValueError, TypeError):
        return None
    d = {
        "contract": CONTRACT_DIRECTIVE,
        "schema_version": SCHEMA_VERSION,
        "mission_id": common["mission_id"],
        "command_id": common["command_id"],
        "device_id": common["device_id"],
        "behavior": behavior,
        # behavior alone is lossy (inspect_zone/capture_photo/wireless_rescan
        # share CHECKPOINT/PATROL) — mission_type preserves the common type.
        "mission_type": mtype,
        "timeout_s": round(timeout_s, 3),
        "expires_at": common["expires_at"],
    }
    if common.get("issued_at"):
        d["issued_at"] = common["issued_at"]
    for f in ("zone_id", "waypoint_id", "route_id"):
        if common.get(f):
            d[f] = common[f]
    if common.get("max_speed_mps") is not None:
        d["max_speed_mps"] = common["max_speed_mps"]
    wps = _resolve_waypoints(common, waypoint_table)
    if wps:
        d["waypoints"] = wps
    # behavior-specific advisory flags
    if mtype == "capture_photo":
        d["capture"] = True
    if mtype == "wireless_rescan":
        d["rescan"] = True
    if mtype == "inspect_zone":
        d["checkpoint"] = True   # inspect = navigate + scan checkpoint
    if mtype == "patrol" and common.get("route_id"):
        d["route_ref"] = common["route_id"]
    bad = _check_strings_ascii(d)
    if bad:
        return None
    return d


def directive_to_common(directive) -> Optional[dict]:
    """Autonomy directive -> common mission (round-trip leg).

    Only mission-typed directives map back; autonomy-native behaviors
    (EXPLORE/COVER/WALL_FOLLOW) return None — they are not missions.
    """
    if not isinstance(directive, Mapping):
        return None
    if directive.get("contract") != CONTRACT_DIRECTIVE \
            or directive.get("schema_version") != SCHEMA_VERSION:
        return None
    behavior = directive.get("behavior")
    mtype = directive.get("mission_type")
    if mtype not in COMMON_MISSION_TYPES:
        mtype = BEHAVIOR_TO_TYPE.get(behavior)
    if mtype is None:
        return None
    out = {
        "contract": CONTRACT_MISSION,
        "schema_version": SCHEMA_VERSION,
        "mission_id": directive.get("mission_id") or "",
        "command_id": directive.get("command_id")
                      or directive.get("mission_id") or "",
        "device_id": directive.get("device_id") or "",
        "type": mtype,
        "expires_at": directive.get("expires_at") or "",
    }
    for f in ("zone_id", "waypoint_id", "route_id", "max_speed_mps",
              "issued_at"):
        if directive.get(f) is not None:
            out[f] = directive[f]
    if directive.get("route_ref") and "route_id" not in out:
        out["route_id"] = directive["route_ref"]
    # module-dispatchable types need the module-required fields; a directive
    # that lacks them cannot round-trip to a module mission — still emit the
    # common object (validation decides module-leg eligibility downstream).
    ok, _ = validate_common_mission(out)
    return out if ok else None


# ---------------------------------------------------------------------------
# Telemetry: autonomy pose/mode report -> common telemetry
# ---------------------------------------------------------------------------

def report_to_common(report, *, device_id: str, provenance: str = "DEMO",
                     observed_at: Optional[str] = None) -> Optional[dict]:
    """autonomy {pose:[x,y,th], mode} report -> common telemetry."""
    if not isinstance(report, Mapping):
        return None
    pose = report.get("pose")
    if not (isinstance(pose, (list, tuple)) and len(pose) >= 3):
        return None
    out = {
        "contract": CONTRACT_TELEMETRY,
        "schema_version": SCHEMA_VERSION,
        "event": "pose_report",
        "device_id": device_id,
        "pose": pose_from_autonomy(pose),
        "provenance": provenance,
        "observed_at": observed_at or _utc_now(),
    }
    if report.get("mode"):
        out["data"] = {"mode": report["mode"]}
    ok, _ = validate_common_telemetry(out)
    return out if ok else None
