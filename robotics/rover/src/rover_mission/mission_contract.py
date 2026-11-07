"""Mission contract validation — docs/04 rover mission contract.

Local, autonomous rejection of unsafe/invalid commands happens HERE, on the
rover, before anything reaches the motor controller. No network required.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .auth import SIGNATURE_FIELD, verify_mission_signature
from .models import MissionType, parse_iso_utc

SCHEMA_VERSION = 1

# Fields each mission type requires beyond the common envelope.
_REQUIRED_FIELDS = {
    MissionType.PATROL_ROUTE: ("route_id",),
    MissionType.INSPECT_ZONE: ("zone_id", "waypoint_id"),
    MissionType.CAPTURE_PHOTO: ("camera_id",),
    MissionType.WIRELESS_RESCAN: ("zone_id",),
    MissionType.RETURN_HOME: (),
    MissionType.STOP: (),
}


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    mission_type: Optional[MissionType] = None


class MissionValidator:
    """Validates docs/04 mission JSON against device config + signature."""

    def __init__(
        self,
        device_id: str,
        secret: bytes,
        max_speed_mps: float = 0.25,
        clock=time.time,
        expiry_skew_s: float = 2.0,
    ):
        self.device_id = device_id
        self.secret = secret
        self.max_speed_mps = max_speed_mps
        self.clock = clock
        self.expiry_skew_s = expiry_skew_s

    def validate(self, mission: dict, known_routes: set, known_waypoints: set,
                 known_zones: set, known_cameras: set) -> ValidationResult:
        # --- envelope ---
        if mission.get("schema_version") != SCHEMA_VERSION:
            return ValidationResult(False, "bad_schema_version")
        for field in ("command_id", "mission_id", "device_id", "type"):
            if not mission.get(field):
                return ValidationResult(False, f"missing_{field}")

        if mission["device_id"] != self.device_id:
            return ValidationResult(False, "wrong_device")

        try:
            mtype = MissionType(mission["type"])
        except ValueError:
            return ValidationResult(False, "unknown_type")

        # --- per-type required fields ---
        for f in _REQUIRED_FIELDS[mtype]:
            if not mission.get(f):
                return ValidationResult(False, f"missing_{f}")

        # --- surveyed-fixture whitelist (no arbitrary coordinates) ---
        if mtype == MissionType.PATROL_ROUTE and mission["route_id"] not in known_routes:
            return ValidationResult(False, "unknown_route")
        if mtype == MissionType.INSPECT_ZONE:
            if mission["waypoint_id"] not in known_waypoints:
                return ValidationResult(False, "unknown_waypoint")
            if mission["zone_id"] not in known_zones:
                return ValidationResult(False, "unknown_zone")
        if mtype == MissionType.WIRELESS_RESCAN and mission["zone_id"] not in known_zones:
            return ValidationResult(False, "unknown_zone")
        if mtype == MissionType.CAPTURE_PHOTO and mission["camera_id"] not in known_cameras:
            return ValidationResult(False, "unknown_camera")

        # --- expiry ---
        expires = mission.get("expires_at")
        if not expires:
            return ValidationResult(False, "missing_expires_at")
        try:
            if parse_iso_utc(expires) <= self.clock() - self.expiry_skew_s:
                return ValidationResult(False, "expired")
        except (ValueError, TypeError):
            return ValidationResult(False, "bad_expires_at")

        # --- speed cap ---
        speed = mission.get("max_speed_mps")
        if speed is not None:
            try:
                if float(speed) > self.max_speed_mps:
                    return ValidationResult(False, "speed_cap")
            except (TypeError, ValueError):
                return ValidationResult(False, "bad_max_speed")

        # --- authentication LAST so structure errors don't leak oracle info,
        #     and so a valid-looking but unsigned mission is still rejected ---
        if not verify_mission_signature(mission, self.secret):
            return ValidationResult(False, "unauthorized")

        return ValidationResult(True, "", mtype)
