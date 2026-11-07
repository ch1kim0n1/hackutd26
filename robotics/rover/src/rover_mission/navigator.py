"""Waypoint navigator — pure-pursuit-style control over surveyed routes.

Drives the ESP32 through turn-in-place / straight primitives (the firmware
has no arc primitive). Operates on the whitelisted waypoint set only;
obstacle_hold and estop states from telemetry gate all motion.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .localization import PoseEstimator
from .models import Pose, Waypoint, wrap_angle
from .motor_link import MotorLink, RoverTelemetry


class NavResult(str, Enum):
    ARRIVED = "arrived"
    IN_PROGRESS = "in_progress"
    OBSTACLE = "obstacle"
    ESTOP = "estop"
    TIMEOUT = "timeout"
    LINK_LOST = "link_lost"


@dataclass
class NavConfig:
    cruise_mmps: int = 200               # below firmware 250 cap
    turn_rate_dps: int = 45
    arrive_dist_mm: float = 60.0
    arrive_heading_rad: float = math.radians(15)
    heading_tolerance_rad: float = math.radians(30)  # turn-in-place threshold
    cmd_ttl_ms: int = 400                # refresh cadence < firmware 500ms watchdog
    waypoint_timeout_s: float = 60.0
    obstacle_patience_s: float = 30.0
    command_prefix: str = "nav"


class Navigator:
    def __init__(self, link: MotorLink, estimator: PoseEstimator,
                 config: Optional[NavConfig] = None):
        self.link = link
        self.estimator = estimator
        self.cfg = config or NavConfig()
        self._cmd_seq = 0
        self._target: Optional[Waypoint] = None
        self._target_since: float = 0.0
        self._obstacle_since: Optional[float] = None
        self._last_telemetry: Optional[RoverTelemetry] = None

    # -- helpers ---------------------------------------------------------
    def _next_cmd_id(self) -> str:
        self._cmd_seq += 1
        return f"{self.cfg.command_prefix}-{self._cmd_seq:05d}-{uuid.uuid4().hex[:6]}"

    def _telemetry(self) -> Optional[RoverTelemetry]:
        tel = self.link.telemetry()
        if tel is not None:
            self._last_telemetry = tel
            # Feed odometry into the estimator (ESP32 reports fused pose).
            prev = self.estimator.pose
            step = math.hypot(tel.pose_x_mm - prev.x_mm, tel.pose_y_mm - prev.y_mm)
            # Only adopt link pose when it changed meaningfully or first fix.
            self.estimator.update_odometry(
                tel.pose_x_mm, tel.pose_y_mm, tel.odom_heading_rad, step
            )
        return tel

    def _send(self, intent: str, **params) -> Optional[dict]:
        params.setdefault("ttl_ms", self.cfg.cmd_ttl_ms)
        return self.link.send_command(intent, self._next_cmd_id(), **params)

    # -- main step --------------------------------------------------------
    def goto(self, waypoint: Waypoint, now: Optional[float] = None) -> NavResult:
        """Advance navigation toward `waypoint` by one control step.

        Call every service tick (~10 Hz). Returns ARRIVED when within
        tolerance; IN_PROGRESS otherwise; OBSTACLE/ESTOP/TIMEOUT/LINK_LOST
        on blocking conditions.
        """
        now = now if now is not None else time.time()
        tel = self._telemetry()

        # --- blocking conditions first ---
        if tel is None:
            return NavResult.LINK_LOST
        if tel.is_estopped:
            self._send("stop")
            return NavResult.ESTOP
        if tel.has_fault and tel.fault == "sensor_fault":
            self._send("stop")
            return NavResult.LINK_LOST

        if self._target is None or self._target.id != waypoint.id:
            self._target = waypoint
            self._target_since = now
            self._obstacle_since = None

        # --- arrival check: position only ---
        # (heading-to-target is meaningless at <1 waypoint radius; bearing
        # to a coincident point is undefined and caused orbit-at-waypoint)
        pose = self.estimator.pose
        dist = pose.distance_to(waypoint.x_mm, waypoint.y_mm)
        herr = pose.heading_error_to(waypoint.x_mm, waypoint.y_mm)
        if dist <= self.cfg.arrive_dist_mm:
            self._send("stop")
            self._target = None
            return NavResult.ARRIVED

        # --- timeouts ---
        if now - self._target_since > self.cfg.waypoint_timeout_s:
            self._send("stop")
            self._target = None
            return NavResult.TIMEOUT

        # --- obstacle: hold position, wait for clear ---
        if tel.is_obstacle:
            self._send("stop")
            if self._obstacle_since is None:
                self._obstacle_since = now
            elif now - self._obstacle_since > self.cfg.obstacle_patience_s:
                self._target = None
                return NavResult.TIMEOUT
            return NavResult.OBSTACLE
        self._obstacle_since = None

        # --- control law: turn-in-place then straight ---
        if abs(herr) > self.cfg.heading_tolerance_rad:
            rate = min(self.cfg.turn_rate_dps,
                       max(15, int(math.degrees(abs(herr)))))
            if herr > 0:
                self._send("turn_left", rate_dps=rate)
            else:
                self._send("turn_right", rate_dps=rate)
        else:
            # Slow near target; never exceed cruise or firmware cap.
            speed = min(self.cfg.cruise_mmps,
                        max(60, int(dist * 0.8)))
            self._send("forward", speed_mmps=speed)
        return NavResult.IN_PROGRESS

    def stop(self) -> None:
        self._send("stop")
        self._target = None

    def current_target(self) -> Optional[Waypoint]:
        return self._target
