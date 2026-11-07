"""RoverService — mission queue, state machine, evidence, telemetry.

Mission lifecycle (docs/03): queued -> accepted -> navigating -> scanning ->
completed | failed | aborted | timed_out. One mission executes at a time;
submissions queue behind the active mission. All validation is local and
autonomous — unsafe commands never reach the motor link.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .auth import sign_mission
from .camera import ArtifactStore, Camera, EvidenceRef, SyntheticCamera
from .localization import NoopDetector, PoseEstimator, TagDetector
from .mission_contract import MissionValidator, ValidationResult
from .models import (
    MissionRecord,
    MissionState,
    MissionType,
    Route,
    Waypoint,
    utc_now_iso,
)
from .motor_link import MotorLink, RoverTelemetry
from .navigator import NavConfig, NavResult, Navigator
from .routes import RouteMap
from .telemetry import ConsolePublisher, Publisher


@dataclass
class ServiceConfig:
    device_id: str = "rover-01"
    secret: bytes = b""
    max_speed_mps: float = 0.25
    tick_s: float = 0.1                    # service loop period (~10 Hz)
    waypoint_settle_s: float = 0.5         # dwell after arrival
    obstacle_mission_patience_s: float = 45.0
    evidence_dir: str = "var/evidence"
    rescan_settle_s: float = 2.0           # time to let puck scan after request


@dataclass
class _ActiveMission:
    record: MissionRecord
    route: Optional[Route] = None
    waypoint_ids: List[str] = field(default_factory=list)
    wp_index: int = 0
    lap: int = 0
    phase: str = "navigate"                # navigate|dwell|capture|rescan|done
    phase_since: float = 0.0
    evidence: List[EvidenceRef] = field(default_factory=list)


class RoverService:
    def __init__(
        self,
        route_map: RouteMap,
        link: MotorLink,
        camera: Optional[Camera] = None,
        detector: Optional[TagDetector] = None,
        publisher: Optional[Publisher] = None,
        config: Optional[ServiceConfig] = None,
        clock=time.time,
    ):
        self.routes = route_map
        self.link = link
        self.cfg = config or ServiceConfig(device_id=route_map.device_id)
        self.clock = clock
        self.validator = MissionValidator(
            device_id=self.cfg.device_id,
            secret=self.cfg.secret,
            max_speed_mps=self.cfg.max_speed_mps,
            clock=clock,
        )
        self.estimator = PoseEstimator(
            tag_to_waypoint={
                w.tag_id: (w.x_mm, w.y_mm)
                for w in route_map.waypoints.values() if w.tag_id is not None
            }
        )
        self.detector = detector or NoopDetector()
        self.camera = camera or SyntheticCamera()
        self._camera_synthetic = isinstance(self.camera, SyntheticCamera)
        self.store = ArtifactStore(self.cfg.evidence_dir)
        self.nav = Navigator(link, self.estimator, NavConfig(
            cruise_mmps=int(self.cfg.max_speed_mps * 1000 * 0.8),
            obstacle_patience_s=self.cfg.obstacle_mission_patience_s,
        ))
        self.publisher = publisher or ConsolePublisher()

        self.missions: List[MissionRecord] = []
        self._queue: List[dict] = []
        self._active: Optional[_ActiveMission] = None
        self._last_tick = clock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def submit(self, mission: dict) -> tuple[bool, str, Optional[MissionRecord]]:
        """Validate + queue a mission. Returns (accepted, reason, record)."""
        known_routes, known_wps, known_zones, known_cams = self.routes.known_ids()
        res = self.validator.validate(
            mission, known_routes, known_wps, known_zones, known_cams
        )
        if not res.ok:
            return False, res.reason, None

        mtype = MissionType(mission["type"])
        record = MissionRecord(
            mission_id=mission["mission_id"],
            command_id=mission["command_id"],
            device_id=mission["device_id"],
            type=mtype,
            zone_id=mission.get("zone_id"),
            waypoint_id=mission.get("waypoint_id"),
            route_id=mission.get("route_id"),
            camera_id=mission.get("camera_id"),
            expires_at=mission.get("expires_at"),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        record.transition(MissionState.QUEUED, "accepted_for_queue")
        self.missions.append(record)
        self._emit(record, "mission_queued")
        self._queue.append({"mission": mission, "record": record})
        return True, "", record

    def abort(self, mission_id: str, reason: str = "operator_abort") -> bool:
        """Abort queued or active mission."""
        if self._active and self._active.record.mission_id == mission_id:
            self._finish_active(MissionState.ABORTED, reason)
            return True
        for i, item in enumerate(self._queue):
            if item["record"].mission_id == mission_id:
                rec = item["record"]
                rec.transition(MissionState.ABORTED, reason)
                self._emit(rec, "mission_aborted")
                del self._queue[i]
                return True
        return False

    def tick(self) -> None:
        """Advance the service one step. Call every cfg.tick_s."""
        now = self.clock()
        self.link.pump()

        if self._active is None and self._queue:
            self._start_next()
        if self._active is not None:
            self._step_active(now)

        # Expiry watchdog for queued missions
        for item in list(self._queue):
            rec = item["record"]
            exp = item["mission"].get("expires_at")
            if exp:
                try:
                    from .models import parse_iso_utc
                    if parse_iso_utc(exp) <= now:
                        rec.transition(MissionState.TIMED_OUT, "expired_in_queue")
                        self._emit(rec, "mission_timed_out")
                        self._queue.remove(item)
                except (ValueError, TypeError):
                    pass

    @property
    def active(self) -> Optional[MissionRecord]:
        return self._active.record if self._active else None

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    # ------------------------------------------------------------------
    # Mission execution
    # ------------------------------------------------------------------
    def _start_next(self) -> None:
        item = self._queue.pop(0)
        mission, record = item["mission"], item["record"]
        mtype = record.type

        active = _ActiveMission(record=record)
        if mtype == MissionType.PATROL_ROUTE:
            route = self.routes.route(record.route_id)
            if route is None:
                record.transition(MissionState.FAILED, "route_missing")
                self._emit(record, "mission_failed")
                return
            active.route = route
            active.waypoint_ids = list(route.waypoint_ids)
            active.lap = 0
        elif mtype == MissionType.INSPECT_ZONE:
            wp = self.routes.waypoint(record.waypoint_id)
            if wp is None:
                record.transition(MissionState.FAILED, "waypoint_missing")
                self._emit(record, "mission_failed")
                return
            active.waypoint_ids = [wp.id]
        elif mtype == MissionType.RETURN_HOME:
            home = self.routes.home()
            if home is None:
                record.transition(MissionState.FAILED, "no_home_waypoint")
                self._emit(record, "mission_failed")
                return
            active.waypoint_ids = [home.id]
        elif mtype == MissionType.CAPTURE_PHOTO:
            active.waypoint_ids = []  # capture in place at current pose
        elif mtype == MissionType.WIRELESS_RESCAN:
            active.waypoint_ids = []
        elif mtype == MissionType.STOP:
            active.waypoint_ids = []

        record.transition(MissionState.ACCEPTED, "mission_started")
        self._emit(record, "mission_accepted")
        self._active = active

    def _step_active(self, now: float) -> None:
        active = self._active
        assert active is not None
        record = active.record
        mtype = record.type

        # Global expiry check
        if record.expires_at:
            try:
                from .models import parse_iso_utc
                if parse_iso_utc(record.expires_at) <= now:
                    self._finish_active(MissionState.TIMED_OUT, "expired")
                    return
            except (ValueError, TypeError):
                pass

        # Link-level faults
        tel = self.link.telemetry()
        if tel is not None and tel.is_estopped:
            self._finish_active(MissionState.ABORTED, "estop_asserted")
            return
        if tel is not None and tel.fault == "watchdog_timeout":
            # Firmware stopped us — treat as failed mission, not silent resume
            self._finish_active(MissionState.FAILED, "motor_watchdog")
            return

        if mtype == MissionType.STOP:
            self.nav.stop()
            self._finish_active(MissionState.COMPLETED, "stop_executed")
            return

        if mtype == MissionType.CAPTURE_PHOTO:
            self._do_capture(active, record)
            return

        if mtype == MissionType.WIRELESS_RESCAN:
            self._do_rescan(active, record, now)
            return

        # Navigation-based missions: patrol / inspect / return_home
        if active.wp_index >= len(active.waypoint_ids):
            self._finish_active(MissionState.COMPLETED, "route_complete")
            return

        wp_id = active.waypoint_ids[active.wp_index]
        wp = self.routes.waypoint(wp_id)
        if wp is None:
            self._finish_active(MissionState.FAILED, f"waypoint_missing:{wp_id}")
            return

        if active.phase == "navigate":
            if record.state != MissionState.NAVIGATING:
                record.transition(MissionState.NAVIGATING, f"to:{wp_id}")
                self._emit(record, "navigating", waypoint_id=wp_id)
            result = self.nav.goto(wp, now=now)
            self._handle_nav_result(active, result, now)
        elif active.phase == "dwell":
            if now - active.phase_since >= wp.dwell_ms / 1000.0:
                self._advance_waypoint(active)
        elif active.phase == "capture":
            self._do_capture(active, record, wp)
        elif active.phase == "rescan":
            if now - active.phase_since >= self.cfg.rescan_settle_s:
                active.evidence.append(EvidenceRef(
                    artifact_id=f"scan-{record.mission_id}-{wp_id}",
                    path="", sha256="", bytes=0,
                    observed_at=utc_now_iso(), zone_id=wp.zone_id,
                    mission_id=record.mission_id, waypoint_id=wp_id,
                    pose=self._pose_dict(),
                ))
                self._advance_waypoint(active)

    def _handle_nav_result(self, active: _ActiveMission, result: NavResult,
                           now: float) -> None:
        record = active.record
        if result == NavResult.ARRIVED:
            wp = self.routes.waypoint(active.waypoint_ids[active.wp_index])
            record.pose_confidence = self.estimator.pose.confidence
            self._detect_and_correct()
            record.pose_confidence = self.estimator.pose.confidence
            # waypoint actions
            if wp is not None and wp.capture:
                active.phase = "capture"
                active.phase_since = now
            elif wp is not None and wp.rescan:
                active.phase = "rescan"
                active.phase_since = now
                self._emit(record, "wireless_rescan_request",
                           zone_id=wp.zone_id, waypoint_id=wp.id)
            elif wp is not None and wp.dwell_ms > 0:
                active.phase = "dwell"
                active.phase_since = now
            else:
                self._advance_waypoint(active)
        elif result == NavResult.TIMEOUT:
            self._finish_active(MissionState.TIMED_OUT, "waypoint_timeout")
        elif result == NavResult.OBSTACLE:
            if record.reason != "obstacle_hold":
                record.transition(MissionState.NAVIGATING, "obstacle_hold")
        elif result == NavResult.ESTOP:
            self._finish_active(MissionState.ABORTED, "estop")
        elif result == NavResult.LINK_LOST:
            self._finish_active(MissionState.FAILED, "link_lost")

    def _advance_waypoint(self, active: _ActiveMission) -> None:
        active.wp_index += 1
        active.phase = "navigate"
        # patrol laps
        if (active.route is not None and active.wp_index >= len(active.waypoint_ids)):
            active.lap += 1
            if active.lap < active.route.laps:
                active.wp_index = 0
                self._emit(active.record, "patrol_lap", lap=active.lap)

    def _detect_and_correct(self) -> None:
        """AprilTag/odometry correction at waypoint arrival (H06/H07 path).

        Captures a frame, runs the tag detector, blends fixes into the pose
        estimator. Detector/camera failures degrade to odometry-only — never
        block the mission.
        """
        try:
            frame = self.camera.capture()
            obs = self.detector.detect(frame)
        except Exception:
            return
        self.estimator.apply_tag_observations(obs)

    def _do_capture(self, active: _ActiveMission, record: MissionRecord,
                    wp: Optional[Waypoint] = None) -> None:
        try:
            frame = self.camera.capture()
        except Exception as exc:
            self._finish_active(MissionState.FAILED, f"camera_error:{exc}")
            return
        zone_id = wp.zone_id if wp else (record.zone_id or "unknown")
        ref = self.store.store(
            frame,
            zone_id=zone_id,
            mission_id=record.mission_id,
            waypoint_id=wp.id if wp else record.waypoint_id,
            pose=self._pose_dict(),
            camera_id=record.camera_id or "cam-mast",
            synthetic=self._camera_synthetic,
        )
        active.evidence.append(ref)
        self._emit(record, "evidence_captured",
                   zone_id=zone_id, waypoint_id=wp.id if wp else None,
                   sha256=ref.sha256, synthetic=ref.synthetic)
        if active.phase == "capture":
            self._advance_waypoint(active)
        else:
            # standalone capture_photo mission
            self._finish_active(MissionState.COMPLETED, "photo_captured")

    def _do_rescan(self, active: _ActiveMission, record: MissionRecord,
                   now: float) -> None:
        if active.phase != "rescan":
            active.phase = "rescan"
            active.phase_since = now
            self._emit(record, "wireless_rescan_request", zone_id=record.zone_id)
            return
        if now - active.phase_since >= self.cfg.rescan_settle_s:
            self._emit(record, "wireless_rescan_done", zone_id=record.zone_id)
            self._finish_active(MissionState.COMPLETED, "rescan_requested")

    def _finish_active(self, state: MissionState, reason: str) -> None:
        active = self._active
        assert active is not None
        active.record.transition(state, reason)
        active.record.pose_confidence = self.estimator.pose.confidence
        self._emit(active.record, f"mission_{state.value}", reason=reason)
        self.nav.stop()
        self._active = None

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------
    def _pose_dict(self) -> dict:
        p = self.estimator.pose
        return {
            "x_mm": round(p.x_mm, 1),
            "y_mm": round(p.y_mm, 1),
            "heading_rad": round(p.heading_rad, 4),
            "confidence": round(p.confidence, 3),
            "source": "esp32_odometry+apriltag",
        }

    def _emit(self, record: MissionRecord, event: str, **extra) -> None:
        tel = self.link.telemetry()
        payload = {
            "event": event,
            "schema_version": 1,
            "device_id": record.device_id,
            "mission_id": record.mission_id,
            "command_id": record.command_id,
            "type": record.type.value,
            "state": record.state.value,
            "zone_id": record.zone_id or extra.get("zone_id"),
            "pose_confidence": round(record.pose_confidence, 3),
            "reason": record.reason or extra.get("reason", ""),
            "observed_at": utc_now_iso(),
            "pose": self._pose_dict(),
        }
        payload.update({k: v for k, v in extra.items() if k not in payload})
        self.publisher.publish(payload)


def make_signed_mission(
    device_id: str,
    secret: bytes,
    mtype: MissionType,
    mission_id: str,
    command_id: str,
    expires_at: str,
    max_speed_mps: float = 0.25,
    **fields,
) -> dict:
    """Helper to build a properly signed mission dict (tests/tools)."""
    mission = {
        "schema_version": 1,
        "command_id": command_id,
        "mission_id": mission_id,
        "device_id": device_id,
        "type": mtype.value,
        "expires_at": expires_at,
        "max_speed_mps": max_speed_mps,
        **fields,
    }
    mission["signature"] = sign_mission(mission, secret)
    return mission
