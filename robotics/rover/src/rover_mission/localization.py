"""Localization: encoder/ToF odometry from the ESP32 + AprilTag correction.

ADR-006: the digital twin represents surveyed geometry and real timestamped
state; no fake localization. Odometry alone drifts — AprilTag sightings
snap the estimate back to surveyed coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Protocol

from .models import Pose


@dataclass
class TagObservation:
    """One AprilTag sighting produced by the camera detector."""

    tag_id: int
    quality: float          # detector confidence 0..1
    dx_mm: float            # tag offset in robot frame (right +)
    dy_mm: float            # tag offset in robot frame (forward +)
    dyaw_rad: float = 0.0   # tag yaw relative to robot heading


class TagDetector(Protocol):
    def detect(self, frame) -> List[TagObservation]: ...


class NoopDetector:
    """Default: no AprilTag library present — odometry only."""

    def detect(self, frame) -> List[TagObservation]:
        return []


class PoseEstimator:
    """Fuses ESP32 odometry telemetry with AprilTag corrections.

    The ESP32 already integrates encoder odometry and reports pose in its
    telemetry; we trust it as the dead-reckoning source and blend AprilTag
    fixes on top. Confidence decays with distance since last tag fix.
    """

    def __init__(self, tag_to_waypoint: dict, confidence_decay_per_m: float = 0.05):
        # tag_id -> (x_mm, y_mm) surveyed position of the tag
        self.tag_to_waypoint = tag_to_waypoint
        self.pose = Pose()
        self._dist_since_fix_mm = 0.0
        self._decay = confidence_decay_per_m

    def reset(self, pose: Optional[Pose] = None) -> None:
        self.pose = pose or Pose()
        self._dist_since_fix_mm = 0.0

    def update_odometry(self, x_mm: float, y_mm: float, heading_rad: float,
                        step_mm: float) -> None:
        """Feed the latest ESP32-reported pose; tracks drift since last fix."""
        self.pose.x_mm = x_mm
        self.pose.y_mm = y_mm
        self.pose.heading_rad = heading_rad
        self._dist_since_fix_mm += abs(step_mm)
        self.pose.confidence = max(
            0.3, 0.95 - self._decay * (self._dist_since_fix_mm / 1000.0)
        )

    def apply_tag_observations(self, obs: List[TagObservation]) -> int:
        """Correct pose from AprilTag sightings. Returns fixes applied."""
        fixes = 0
        for o in obs:
            wp = self.tag_to_waypoint.get(o.tag_id)
            if wp is None or o.quality < 0.4:
                continue
            # Tag at surveyed (tx,ty); robot sits dx forward / dy right of it
            # in the tag's frame, rotated by tag yaw + robot-relative yaw.
            tag_x, tag_y = wp
            yaw = o.dyaw_rad
            # robot position = tag pos - R(yaw_tag_world) * (dx,dy)
            # we approximate tag world yaw = 0 unless surveyed otherwise;
            # heading correction blends measured dyaw.
            rx = tag_x - (o.dx_mm * math.cos(yaw) - o.dy_mm * math.sin(yaw))
            ry = tag_y - (o.dx_mm * math.sin(yaw) + o.dy_mm * math.cos(yaw))
            est_heading = self.pose.heading_rad - o.dyaw_rad

            # Blend: weight by detector quality; hard snap on very good fixes.
            w = min(1.0, o.quality)
            if w >= 0.9:
                self.pose.x_mm, self.pose.y_mm = rx, ry
                self.pose.heading_rad = wrap(est_heading)
            else:
                self.pose.x_mm += (rx - self.pose.x_mm) * w
                self.pose.y_mm += (ry - self.pose.y_mm) * w
                self.pose.heading_rad = wrap(
                    self.pose.heading_rad + (est_heading - self.pose.heading_rad) * w
                )
            self._dist_since_fix_mm = 0.0
            self.pose.confidence = min(0.99, 0.7 + 0.3 * o.quality)
            fixes += 1
        return fixes


def wrap(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a
