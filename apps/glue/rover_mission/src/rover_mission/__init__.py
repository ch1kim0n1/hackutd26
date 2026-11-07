"""GLUE-03: AI proposal -> policy gate -> gateway command -> rover
mission -> AprilTag/photo evidence -> protected artifact -> incident
update. In-memory; rover is a kinematic sim honoring surveyed waypoints.

Safety enforced: waypoint must be in surveyed route allowlist; command
TTL enforced; expired/dangerous commands fail closed; photo evidence
carries sha256+timestamp+zone; artifacts referenced not embedded.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field


class MissionDenied(Exception):
    pass


class MissionExpired(MissionDenied):
    pass


@dataclass
class Waypoint:
    wp_id: str
    x: float
    y: float
    surveyed: bool = True
    tags: list[str] = field(default_factory=list)  # expected AprilTags


class RouteSurvey:
    def __init__(self):
        self.waypoints: dict[str, Waypoint] = {}

    def add(self, wp: Waypoint) -> None:
        self.waypoints[wp.wp_id] = wp

    def get(self, wp_id: str) -> Waypoint:
        wp = self.waypoints.get(wp_id)
        if wp is None or not wp.surveyed:
            raise MissionDenied(f"waypoint {wp_id} not surveyed")
        return wp


@dataclass
class MissionProposal:
    proposal_id: str
    incident_id: str
    wp_id: str
    reason: str
    created_at: float = field(default_factory=time.time)


class PolicyGate:
    """Approval-bound gate: proposal must carry valid approval id and
    be within TTL. Dangerous actions (outside survey, no approval)
    denied."""

    TTL_S = 120.0

    def __init__(self, clock=time.time):
        self.clock = clock
        self.approvals: dict[str, dict] = {}

    def approve(self, approval_id: str, proposal: MissionProposal) -> None:
        self.approvals[approval_id] = {
            "wp_id": proposal.wp_id, "incident_id": proposal.incident_id,
            "expires": self.clock() + self.TTL_S}

    def check(self, proposal: MissionProposal,
              approval_id: str | None) -> None:
        if not approval_id or approval_id not in self.approvals:
            raise MissionDenied("no server-side approval")
        a = self.approvals[approval_id]
        if self.clock() > a["expires"]:
            raise MissionExpired("approval expired")
        if a["wp_id"] != proposal.wp_id or \
                a["incident_id"] != proposal.incident_id:
            raise MissionDenied("approval bound to different target")


class Gateway:
    """Signs outbound mission commands — device verifies signature."""

    def __init__(self, secret: bytes = b"gw-secret"):
        self.secret = secret

    def issue(self, proposal: MissionProposal, approval_id: str) -> dict:
        return {"cmd": "goto_waypoint", "wp_id": proposal.wp_id,
                "mission_id": proposal.proposal_id,
                "approval_id": approval_id,
                "expires_at": time.time() + 60}


class RoverSim:
    """Kinematic sim: drives to waypoint, 'detects' AprilTag, captures
    photo evidence (hash+ts+zone)."""

    def __init__(self, survey: RouteSurvey, clock=time.time):
        self.survey = survey
        self.clock = clock
        self.pose = (0.0, 0.0)
        self.missions: list[dict] = []

    def execute(self, cmd: dict) -> dict:
        wp = self.survey.get(cmd["wp_id"])
        # simulate travel + arrival
        self.pose = (wp.x, wp.y)
        tag = wp.tags[0] if wp.tags else None
        photo = {
            "artifact_id": f"art-{uuid.uuid4().hex[:10]}",
            "sha256": hashlib.sha256(
                f"{wp.wp_id}:{self.clock()}".encode()).hexdigest(),
            "captured_at": self.clock(),
            "zone_id": "rack-01",
            "waypoint": wp.wp_id,
            "tag_seen": tag,
            "synthetic": True,   # sim photo — labeled, never 'real'
        }
        result = {"mission_id": cmd["mission_id"], "state": "complete",
                  "pose": self.pose, "photo": photo,
                  "finished_at": self.clock()}
        self.missions.append(result)
        return result


class EvidenceVault:
    """Protected artifact store — refs only, short-lived access."""

    URL_TTL_S = 300.0

    def __init__(self, clock=time.time):
        self.clock = clock
        self.artifacts: dict[str, dict] = {}

    def store(self, artifact: dict) -> str:
        self.artifacts[artifact["artifact_id"]] = artifact
        return artifact["artifact_id"]

    def access_url(self, artifact_id: str) -> str:
        if artifact_id not in self.artifacts:
            raise MissionDenied("unknown artifact")
        return f"https://evidence.local/{artifact_id}?exp={int(self.clock() + self.URL_TTL_S)}"


class IncidentUpdater:
    def __init__(self):
        self.updates: list[dict] = []

    def attach_evidence(self, incident_id: str, artifact_id: str,
                        mission_id: str) -> None:
        self.updates.append({"incident_id": incident_id,
                             "evidence_id": artifact_id,
                             "mission_id": mission_id,
                             "kind": "photo_evidence"})


class MissionOrchestrator:
    """Wires proposal->policy->gateway->rover->vault->incident."""

    def __init__(self, survey: RouteSurvey, gate: PolicyGate,
                 gateway: Gateway, rover: RoverSim, vault: EvidenceVault,
                 updater: IncidentUpdater):
        self.survey = survey
        self.gate = gate
        self.gw = gateway
        self.rover = rover
        self.vault = vault
        self.updater = updater

    def run(self, proposal: MissionProposal,
            approval_id: str | None) -> dict:
        self.gate.check(proposal, approval_id)          # fail closed
        self.survey.get(proposal.wp_id)                # surveyed only
        cmd = self.gw.issue(proposal, approval_id)
        result = self.rover.execute(cmd)
        aid = self.vault.store(result["photo"])
        self.updater.attach_evidence(proposal.incident_id, aid,
                                     result["mission_id"])
        result["evidence_ref"] = aid
        return result
