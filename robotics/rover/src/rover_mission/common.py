"""Shared rover mission/telemetry/evidence contract — ``sentinel.rover.*`` v1.

Issue #115 / docs/14. One versioned schema that the four rover stacks map
to and from:

  autonomy/                onboard behavior engine (sim + real)
  robotics/rover           signed mission runtime (this package)
  services/mission-shim    module commandJson -> signed rover mission
  spacetimedb module       mission authority (commandJson + state machine)

Nothing here changes enforcement: HMAC signing, surveyed-fixture whitelists,
expiry and E-stop stay exactly where they are (``mission_contract.py``,
``service.py``, ``auth.py``). This module only defines the shared
vocabulary and lossless mapping tables so each stack's native format can be
translated without semantic drift. ``autonomy/mission_map.py`` is a
self-contained port of the autonomy-side mapping (autonomy deploys to the
Pi as flat scripts and cannot import this package); the parity test in
``tests/test_common_contract.py`` keeps the two implementations honest.
"""

from __future__ import annotations

from typing import Mapping, Optional

from .auth import sign_mission
from .models import MissionType, parse_iso_utc

SCHEMA_VERSION = 1

CONTRACT_MISSION = "sentinel.rover.mission"
CONTRACT_TELEMETRY = "sentinel.rover.telemetry"
CONTRACT_EVIDENCE = "sentinel.rover.evidence"

# Provenance vocabulary is frozen by docs/13 — simulated data is never LIVE.
PROVENANCE_VALUES = frozenset({"DEMO", "REPLAY", "LIVE"})

# ---------------------------------------------------------------------------
# Mission types
#
# Canonical common vocabulary = the SpacetimeDB module MissionType enum
# (schema.ts, frozen upstream contract) plus exactly one device-local
# extension, ``wireless_rescan``, which the module cannot dispatch (no
# MISSION_TYPES entry in reducers-mission.ts). Rover-native spellings map
# onto the canonical vocabulary; they are never canonical themselves.
# ---------------------------------------------------------------------------

COMMON_MISSION_TYPES = frozenset({
    "inspect_zone",
    "patrol",
    "capture_photo",
    "return_home",
    "hold",
    "wireless_rescan",  # device-local only — see docs/14 §5
})
MODULE_MISSION_TYPES = frozenset({
    "inspect_zone", "patrol", "capture_photo", "return_home", "hold",
})
ROVER_MISSION_TYPES = frozenset({
    "inspect_zone", "patrol_route", "capture_photo",
    "wireless_rescan", "return_home", "stop",
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
# module commandJson type == common type for every module-dispatchable type.
TYPE_TO_MODULE = {t: t for t in MODULE_MISSION_TYPES}

# Fields each common mission type requires at the COMMON level (docs/14 §3).
# This is the union envelope — looser than any single stack. Module-dispatchable
# types additionally require zone_id + waypoint_id + the module speed window,
# enforced at the module boundary (common_to_module_command), because the
# module reducers demand them (validateMissionTarget/Window).
MISSION_REQUIRED_FIELDS = {
    "inspect_zone": ("zone_id", "waypoint_id"),
    "patrol": (),          # needs a route selector: waypoint_id OR route_id
    "capture_photo": (),
    "return_home": (),
    "hold": (),
    "wireless_rescan": ("zone_id",),
}
# patrol is valid with EITHER selector — waypoint_id (module/shim path) or
# route_id (direct rover path, e.g. hand-authored rover missions).
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
# Module speed window — reducers-mission.ts validateMissionWindow.
MODULE_SPEED_MIN_EXCLUSIVE = 0.05
MODULE_SPEED_MAX = 0.5

# ---------------------------------------------------------------------------
# Mission states
#
# Common vocabulary = union of module MissionState (schema.ts) and rover
# MissionState (models.py). Module-side states are never device-reported;
# rover-side substates are documented projections, not new authority.
# ---------------------------------------------------------------------------

MODULE_STATES = frozenset({
    "proposed", "approved", "dispatched",
    "accepted", "navigating",
    "completed", "failed", "expired", "cancelled",
})
ROVER_STATES = frozenset({
    "queued", "accepted", "navigating", "scanning",
    "completed", "failed", "aborted", "timed_out",
})
COMMON_STATES = MODULE_STATES | ROVER_STATES

# The only states a device may legally report to the module — enforced by
# DEVICE_STATES in reducers-mission.ts and MISSION_STATUS_DEVICE_STATES in
# lib.ts applyMissionStatus. Anything else is skipped module-side.
MODULE_DEVICE_STATES = frozenset({"accepted", "navigating", "completed", "failed"})

# Common/rover state -> module device-reportable state. ``None`` means the
# state has no device-reportable form (module-side lifecycle states, or
# pre-acceptance queueing which leaves the module mission at 'dispatched').
# aborted/timed_out project to 'failed' — the native outcome is preserved in
# the event name + reason, never silently upgraded to 'completed'.
STATE_TO_MODULE_DEVICE = {
    "accepted": "accepted",
    "navigating": "navigating",
    "scanning": "navigating",   # rover sub-phase of navigating; see docs/14 §4
    "completed": "completed",
    "failed": "failed",
    "aborted": "failed",
    "timed_out": "failed",
    "queued": None,
    "proposed": None,
    "approved": None,
    "dispatched": None,
    "expired": None,
    "cancelled": None,
}

# Common state -> rover MissionState.value, for states the rover can express.
STATE_TO_ROVER = {s: s for s in ROVER_STATES}

# ---------------------------------------------------------------------------
# Pose — the one place unit/frame ambiguity is forbidden to hide.
# autonomy/ works in metres in its own map frame; the rover works in mm in
# the surveyed floor-plan frame. Poses are NEVER comparable across frames —
# the twin bridge (#116) owns frame alignment.
# ---------------------------------------------------------------------------

POSE_UNITS = frozenset({"mm", "m"})
ROVER_POSE_UNIT = "mm"
ROVER_POSE_FRAME = "surveyed_floorplan"
AUTONOMY_POSE_UNIT = "m"
AUTONOMY_POSE_FRAME = "autonomy_map"


def _is_str(v) -> bool:
    return isinstance(v, str) and len(v) > 0


def _is_ascii(v) -> bool:
    return isinstance(v, str) and all(ord(c) < 128 for c in v)


def _valid_pose(p) -> bool:
    return (
        isinstance(p, Mapping)
        and isinstance(p.get("x"), (int, float))
        and isinstance(p.get("y"), (int, float))
        and isinstance(p.get("heading_rad"), (int, float))
        and p.get("unit") in POSE_UNITS
        and _is_str(p.get("frame"))
    )


def pose_from_rover(pose: Mapping) -> dict:
    """rover_mission pose dict {x_mm,y_mm,heading_rad,confidence,source}
    -> common pose (mm, surveyed frame)."""
    out = {
        "x": pose.get("x_mm"),
        "y": pose.get("y_mm"),
        "heading_rad": pose.get("heading_rad"),
        "unit": ROVER_POSE_UNIT,
        "frame": ROVER_POSE_FRAME,
    }
    if pose.get("confidence") is not None:
        out["confidence"] = pose["confidence"]
    if pose.get("source"):
        out["source"] = pose["source"]
    return out


def pose_from_autonomy(pose, *, source: str = "odometry+scan_match") -> dict:
    """autonomy pose [x, y, theta] metres -> common pose."""
    x, y, th = pose[0], pose[1], pose[2]
    return {
        "x": x, "y": y, "heading_rad": th,
        "unit": AUTONOMY_POSE_UNIT, "frame": AUTONOMY_POSE_FRAME,
        "source": source,
    }


# ---------------------------------------------------------------------------
# Mission validators
# ---------------------------------------------------------------------------

def _check_strings_ascii(m: Mapping) -> Optional[str]:
    for k, v in m.items():
        if isinstance(v, str) and not _is_ascii(v):
            return f"non-ascii field {k}"
    return None


def validate_common_mission(m) -> tuple[bool, str]:
    """Validate a sentinel.rover.mission/v1 object. Returns (ok, reason)."""
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
        parse_iso_utc(expires)
    except (ValueError, TypeError):
        return False, "bad_expires_at"
    return True, ""


def validate_common_telemetry(t) -> tuple[bool, str]:
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
        parse_iso_utc(t["observed_at"])
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


def validate_common_evidence(e) -> tuple[bool, str]:
    if not isinstance(e, Mapping):
        return False, "not an object"
    if e.get("contract") != CONTRACT_EVIDENCE:
        return False, "bad_contract"
    if e.get("schema_version") != SCHEMA_VERSION:
        return False, "bad_schema_version"
    for f in ("artifact_id", "mission_id", "device_id", "zone_id",
              "observed_at", "storage_ref"):
        if not _is_str(e.get(f)):
            return False, f"missing_{f}"
    sha = e.get("sha256")
    if not _is_str(sha) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        return False, "bad_sha256"
    if not isinstance(e.get("bytes"), int) or isinstance(e.get("bytes"), bool) \
            or e["bytes"] < 0:
        return False, "bad_bytes"
    if e.get("provenance") not in PROVENANCE_VALUES:
        return False, "bad_provenance"
    if not isinstance(e.get("synthetic"), bool):
        return False, "missing_synthetic"
    for f in ("command_id", "waypoint_id", "camera_id"):
        if e.get(f) is not None and not _is_str(e[f]):
            return False, f"bad_{f}"
    if e.get("pose") is not None and not _valid_pose(e["pose"]):
        return False, "bad_pose"
    try:
        parse_iso_utc(e["observed_at"])
    except (ValueError, TypeError):
        return False, "bad_observed_at"
    return True, ""


# ---------------------------------------------------------------------------
# Mission mappers
# ---------------------------------------------------------------------------

def _common_mission_from(m: Mapping, mtype: str) -> dict:
    out = {
        "contract": CONTRACT_MISSION,
        "schema_version": SCHEMA_VERSION,
        "mission_id": m["mission_id"],
        "command_id": m.get("command_id") or m["mission_id"],
        "device_id": m["device_id"],
        "type": mtype,
    }
    for f in ("zone_id", "waypoint_id", "route_id", "camera_id",
              "expires_at", "max_speed_mps", "issued_at"):
        if m.get(f) is not None:
            out[f] = m[f]
    return out


def module_command_to_common(cmd) -> Optional[dict]:
    """SpacetimeDB commandJson -> common mission. None if not module-shaped."""
    if not isinstance(cmd, Mapping) or cmd.get("schema_version") != SCHEMA_VERSION:
        return None
    mtype = cmd.get("type")
    if mtype not in MODULE_MISSION_TYPES:
        return None
    mission_id = cmd.get("mission_id")
    if not _is_str(mission_id) or not _is_str(cmd.get("device_id")):
        return None
    common = _common_mission_from(cmd, mtype)
    ok, _ = validate_common_mission(common)
    return common if ok else None


def common_to_module_command(common) -> Optional[dict]:
    """Common mission -> SpacetimeDB commandJson.

    None when the mission is not module-dispatchable (wireless_rescan) or
    fails module-required fields (zone_id + waypoint_id for every type,
    max_speed_mps inside the module window). The module format intentionally
    carries no route_id/camera_id — those are shim/rover resolution details.
    """
    ok, _ = validate_common_mission(common)
    if not ok or common["type"] not in MODULE_MISSION_TYPES:
        return None
    mtype = common["type"]
    for f in MODULE_REQUIRED_FIELDS[mtype]:
        if not _is_str(common.get(f)):
            return None
    speed = common.get("max_speed_mps")
    if not isinstance(speed, (int, float)) or isinstance(speed, bool) \
            or not (MODULE_SPEED_MIN_EXCLUSIVE < float(speed)
                    <= MODULE_SPEED_MAX):
        return None
    out = {
        "schema_version": SCHEMA_VERSION,
        "command_id": common["command_id"],
        "mission_id": common["mission_id"],
        "device_id": common["device_id"],
        "type": common["type"],
        "zone_id": common["zone_id"],
        "waypoint_id": common["waypoint_id"],
        "expires_at": common["expires_at"],
        "max_speed_mps": common["max_speed_mps"],
    }
    return out


def rover_mission_to_common(mission) -> Optional[dict]:
    """Signed/unsigned rover mission dict -> common mission (signature is a
    transport concern and is never part of the common object)."""
    if not isinstance(mission, Mapping):
        return None
    rtype = mission.get("type")
    if rtype not in ROVER_MISSION_TYPES:
        return None
    mission_id = mission.get("mission_id")
    if not _is_str(mission_id) or not _is_str(mission.get("device_id")):
        return None
    common = _common_mission_from(mission, TYPE_FROM_ROVER[rtype])
    ok, _ = validate_common_mission(common)
    return common if ok else None


def _rover_type_fields(mtype: str, common: Mapping,
                       routes: Optional[Mapping], camera_id: str) -> Optional[dict]:
    """Mirror of mission-shim transform.ts field rules (Python port)."""
    rtype = TYPE_TO_ROVER[mtype]
    out = {"type": rtype}
    zone_id = common.get("zone_id")
    waypoint_id = common.get("waypoint_id")
    if rtype == "inspect_zone":
        if not _is_str(zone_id) or not _is_str(waypoint_id):
            return None
        out["zone_id"], out["waypoint_id"] = zone_id, waypoint_id
    elif rtype == "patrol_route":
        # shim: waypoint_id ? routes[waypoint] ?? routes['*'] : routes['*']
        route_id = common.get("route_id")
        if route_id is None and routes is not None:
            if _is_str(waypoint_id) and waypoint_id in routes:
                route_id = routes[waypoint_id]
            else:
                route_id = routes.get("*")
        if not _is_str(route_id):
            return None
        out["route_id"] = route_id
    elif rtype == "capture_photo":
        out["camera_id"] = camera_id or "cam-mast"
    elif rtype == "wireless_rescan":
        if not _is_str(zone_id):
            return None
        out["zone_id"] = zone_id
        if _is_str(waypoint_id):
            out["waypoint_id"] = waypoint_id
    # return_home / stop carry no extra fields
    return out


def _build_rover_mission(common, *, device_id: str, routes, camera_id,
                         secret: bytes) -> Optional[dict]:
    """common -> signed rover mission dict. Ports transform.ts semantics:
    type map, route/camera resolution, ASCII guard, HMAC signature.

    Module-dispatchable types must pass the module leg first — the shim only
    signs missions the module could have authorized (zone/waypoint whitelists
    and the speed window are enforced module-side). The two device-local
    exceptions never traverse the module: ``wireless_rescan`` (no module
    type) and ``patrol`` carrying an explicit ``route_id`` (rover-native
    form). This mirrors mission-shim common.ts exactly."""
    ok, _ = validate_common_mission(common)
    if not ok or common.get("device_id") != device_id:
        return None
    mtype = common["type"]
    device_local = (
        mtype == "wireless_rescan"
        or (mtype == "patrol" and _is_str(common.get("route_id")))
    )
    if not device_local and common_to_module_command(common) is None:
        return None
    fields = _rover_type_fields(mtype, common, routes, camera_id)
    if fields is None:
        return None
    mission = {
        "schema_version": SCHEMA_VERSION,
        "command_id": common["command_id"],
        "mission_id": common["mission_id"],
        "device_id": device_id,
        "expires_at": common["expires_at"],
        **fields,
    }
    if common.get("max_speed_mps") is not None:
        mission["max_speed_mps"] = common["max_speed_mps"]
    bad = _check_strings_ascii(mission)
    if bad:
        return None
    mission["signature"] = sign_mission(mission, secret)
    return mission


def common_to_rover_mission(common, *, device_id: str, secret: bytes,
                            routes: Optional[Mapping] = None,
                            camera_id: str = "cam-mast") -> Optional[dict]:
    """Common mission -> signed rover mission (the mission-shim role,
    implemented in Python for tests and non-TS consumers)."""
    if not isinstance(common, Mapping):
        return None
    return _build_rover_mission(common, device_id=device_id, routes=routes,
                                camera_id=camera_id, secret=secret)


# ---------------------------------------------------------------------------
# Telemetry mappers
# ---------------------------------------------------------------------------

def _common_pose_from_rover_event(pose: Mapping) -> dict:
    return pose_from_rover(pose)


def rover_event_to_common(event, *, provenance: str = "DEMO") -> Optional[dict]:
    """rover_mission _emit payload -> common telemetry. ``provenance`` is
    caller-supplied: SimulatedLink runs are DEMO, Esp32SerialLink LIVE."""
    if not isinstance(event, Mapping):
        return None
    if event.get("schema_version") != SCHEMA_VERSION:
        return None
    if not _is_str(event.get("event")) or not _is_str(event.get("device_id")):
        return None
    rtype = event.get("type")
    rstate = event.get("state")
    out = {
        "contract": CONTRACT_TELEMETRY,
        "schema_version": SCHEMA_VERSION,
        "event": event["event"],
        "device_id": event["device_id"],
        "observed_at": event.get("observed_at") or "",
        "provenance": provenance,
    }
    for f in ("mission_id", "command_id", "zone_id", "waypoint_id", "reason"):
        if event.get(f):
            out[f] = event[f]
    if rtype in ROVER_MISSION_TYPES:
        out["type"] = TYPE_FROM_ROVER[rtype]
    if rstate in ROVER_STATES:
        out["state"] = rstate
    if isinstance(event.get("pose"), Mapping):
        out["pose"] = _common_pose_from_rover_event(event["pose"])
    extras = {k: v for k, v in event.items()
              if k not in _ROVER_EVENT_ENVELOPE}
    if extras:
        out["data"] = extras
    ok, _ = validate_common_telemetry(out)
    return out if ok else None


_ROVER_EVENT_ENVELOPE = frozenset({
    "event", "schema_version", "device_id", "mission_id", "command_id",
    "type", "state", "zone_id", "waypoint_id", "pose_confidence", "reason",
    "observed_at", "pose",
})


def autonomy_report_to_common(report, *, device_id: str,
                              provenance: str = "DEMO",
                              observed_at: Optional[str] = None) -> Optional[dict]:
    """autonomy pose/mode report {pose:[x,y,th], mode} -> common telemetry
    (pose_report event; the Brain mode is preserved under data.mode)."""
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


def _utc_now() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def module_report_fields(state: str, reason: str = "") -> Optional[dict]:
    """Common/native state -> the {state, reason} pair a device may legally
    report to the module (recordMissionResult / applyMissionStatus).

    Returns None for states with no device-reportable form. Native outcome
    detail is preserved as a ``<native>:<reason>`` prefix so aborted/timed_out
    never masquerade as ordinary failures.
    """
    mapped = STATE_TO_MODULE_DEVICE.get(state)
    if mapped is None:
        return None
    return {"state": mapped, "reason": f"{state}:{reason}" if reason else state}


# ---------------------------------------------------------------------------
# Evidence mappers
# ---------------------------------------------------------------------------

def evidence_to_common(evidence, *, device_id: str = "",
                       provenance: Optional[str] = None,
                       mission_id: str = "") -> Optional[dict]:
    """Rover EvidenceRef / artifact sidecar meta -> common evidence.

    ``synthetic`` artifacts are DEMO provenance unless overridden — sim
    evidence is never presented as LIVE (docs/13).
    """
    if not isinstance(evidence, Mapping):
        return None
    artifact_id = evidence.get("artifact_id")
    sha = evidence.get("sha256")
    if not _is_str(artifact_id) or not _is_str(sha):
        return None
    synthetic = bool(evidence.get("synthetic", False))
    prov = provenance or ("DEMO" if synthetic else "LIVE")
    out = {
        "contract": CONTRACT_EVIDENCE,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "mission_id": mission_id or evidence.get("mission_id") or "",
        "device_id": device_id or evidence.get("device_id") or "",
        "zone_id": evidence.get("zone_id") or "",
        "observed_at": evidence.get("observed_at") or "",
        "storage_ref": evidence.get("storage_ref") or evidence.get("path") or "",
        "sha256": sha,
        "bytes": evidence.get("bytes", 0),
        "synthetic": synthetic,
        "provenance": prov,
    }
    for f in ("command_id", "waypoint_id", "camera_id", "received_at",
              "width", "height", "format"):
        if evidence.get(f) is not None:
            out[f] = evidence[f]
    if isinstance(evidence.get("pose"), Mapping):
        out["pose"] = pose_from_rover(evidence["pose"])
    ok, _ = validate_common_evidence(out)
    return out if ok else None


def common_to_module_evidence_row(common, *, incident_id: str,
                                  trust_tier: str, trace_id: str) -> Optional[dict]:
    """Common evidence -> SpacetimeDB evidence row shape (schema.ts).

    The module row is incident-scoped metadata; the artifact binary stays
    outside the DB (ADR-008) — storage_ref is the pointer, sha256 the
    integrity anchor.
    """
    ok, _ = validate_common_evidence(common)
    if not ok:
        return None
    source = common.get("camera_id") or "rover-camera"
    return {
        "incidentId": incident_id,
        "source": f"rover/{common['device_id']}/{source}",
        "observedAt": common["observed_at"],
        "storageRef": common["storage_ref"],
        "sha256": common["sha256"],
        "trustTier": trust_tier,
        "traceId": trace_id,
    }
