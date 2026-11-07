"""Core data types for the rover mission runtime."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MissionState(str, Enum):
    """docs/03 rover behavior states."""

    QUEUED = "queued"
    ACCEPTED = "accepted"
    NAVIGATING = "navigating"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    TIMED_OUT = "timed_out"


TERMINAL_STATES = {
    MissionState.COMPLETED,
    MissionState.FAILED,
    MissionState.ABORTED,
    MissionState.TIMED_OUT,
}


class MissionType(str, Enum):
    PATROL_ROUTE = "patrol_route"
    INSPECT_ZONE = "inspect_zone"
    CAPTURE_PHOTO = "capture_photo"
    WIRELESS_RESCAN = "wireless_rescan"
    RETURN_HOME = "return_home"
    STOP = "stop"


@dataclass
class Pose:
    """Rover pose in the surveyed floor-plan frame (mm, radians)."""

    x_mm: float = 0.0
    y_mm: float = 0.0
    heading_rad: float = 0.0
    confidence: float = 0.5  # 0..1 evidence quality, not model certainty

    def distance_to(self, x_mm: float, y_mm: float) -> float:
        return ((self.x_mm - x_mm) ** 2 + (self.y_mm - y_mm) ** 2) ** 0.5

    def heading_error_to(self, x_mm: float, y_mm: float) -> float:
        desired = math.atan2(y_mm - self.y_mm, x_mm - self.x_mm)
        return wrap_angle(desired - self.heading_rad)


def wrap_angle(a: float) -> float:
    while a > 3.141592653589793:
        a -= 2 * 3.141592653589793
    while a < -3.141592653589793:
        a += 2 * 3.141592653589793
    return a


@dataclass
class Waypoint:
    id: str
    zone_id: str
    x_mm: float
    y_mm: float
    tag_id: Optional[int] = None       # AprilTag id mounted at this spot
    capture: bool = False              # take photo evidence on arrival
    rescan: bool = False               # request wireless rescan on arrival
    dwell_ms: int = 0                  # pause at waypoint (scan/photo time)


@dataclass
class Zone:
    id: str
    name: str
    bounds: dict = field(default_factory=dict)  # {x_min,y_min,x_max,y_max} mm
    waypoints: list = field(default_factory=list)


@dataclass
class Route:
    id: str
    name: str
    waypoint_ids: list
    laps: int = 1                      # patrol_route laps per mission


@dataclass
class MissionRecord:
    """Runtime record of one accepted mission (docs/04 missions table)."""

    mission_id: str
    command_id: str
    device_id: str
    type: MissionType
    state: MissionState = MissionState.QUEUED
    zone_id: Optional[str] = None
    waypoint_id: Optional[str] = None
    route_id: Optional[str] = None
    camera_id: Optional[str] = None
    reason: str = ""
    pose_confidence: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    expires_at: Optional[str] = None
    events: list = field(default_factory=list)

    def transition(self, new_state: MissionState, reason: str = "") -> None:
        self.state = new_state
        self.reason = reason
        self.updated_at = utc_now_iso()
        self.events.append(
            {
                "at": self.updated_at,
                "state": new_state.value,
                "reason": reason,
            }
        )


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_iso_utc(s: str) -> float:
    """Parse ISO-8601 UTC timestamp to epoch seconds. Accepts trailing Z."""
    from datetime import datetime, timezone

    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    return datetime.fromisoformat(t).astimezone(timezone.utc).timestamp()
