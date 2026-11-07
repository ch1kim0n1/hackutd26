"""Incident record model + state machine — docs/06 R03, docs/04.

Fields mirror the `incidents` table contract: severity, confidence,
ownership, timestamps, provenance, evidence refs, version, state."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class IncidentState(str, Enum):
    NEW = "new"
    TRIAGE = "triage"
    INVESTIGATING = "investigating"
    CONTAINMENT_PENDING = "containment_pending"
    CONTAINED = "contained"
    RECOVERY = "recovery"
    RESOLVED = "resolved"
    CLOSED = "closed"
    DISMISSED = "dismissed"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# allowed transitions — anything else rejected
TRANSITIONS: dict[IncidentState, set[IncidentState]] = {
    IncidentState.NEW: {IncidentState.TRIAGE, IncidentState.DISMISSED,
                        IncidentState.INVESTIGATING},
    IncidentState.TRIAGE: {IncidentState.INVESTIGATING, IncidentState.DISMISSED,
                          IncidentState.NEW},
    IncidentState.INVESTIGATING: {IncidentState.CONTAINMENT_PENDING,
                                  IncidentState.RESOLVED,
                                  IncidentState.DISMISSED, IncidentState.TRIAGE},
    IncidentState.CONTAINMENT_PENDING: {IncidentState.CONTAINED,
                                        IncidentState.INVESTIGATING},
    IncidentState.CONTAINED: {IncidentState.RECOVERY, IncidentState.RESOLVED},
    IncidentState.RECOVERY: {IncidentState.RESOLVED, IncidentState.CONTAINED},
    IncidentState.RESOLVED: {IncidentState.CLOSED},
    IncidentState.CLOSED: set(),
    IncidentState.DISMISSED: set(),
}
TERMINAL = {IncidentState.CLOSED, IncidentState.DISMISSED}


@dataclass
class EvidenceRef:
    evidence_id: str
    kind: str               # observation|frame|artifact|chat|audit
    note: str = ""
    added_by: str = ""
    added_at: float = field(default_factory=time.time)


@dataclass
class TimelineEvent:
    seq: int
    at: float
    actor_id: str
    kind: str               # created|field_edit|state_change|evidence_add|
                            # note|assignment|export
    detail: dict


@dataclass
class Incident:
    incident_id: str
    title: str
    summary: str = ""
    state: IncidentState = IncidentState.NEW
    severity: Severity = Severity.MEDIUM
    confidence: float = 0.0          # 0..1 model/human confidence
    owner_id: str = ""               # accountable human
    zone_id: str = ""
    created_by: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1                 # optimistic concurrency counter
    evidence: list[EvidenceRef] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)  # source system/trace ids
    notes: list[dict] = field(default_factory=list)

    # editable fields (everything else is structural)
    EDITABLE = {"title", "summary", "severity", "confidence",
                "owner_id", "zone_id"}

    def editable_snapshot(self) -> dict:
        return {f: getattr(self, f) for f in self.EDITABLE}


class VersionConflict(Exception):
    """Optimistic concurrency: client's expected_version is stale —
    visible conflict, never silent overwrite (docs/04)."""
    def __init__(self, incident_id: str, current_version: int):
        super().__init__(
            f"incident {incident_id} at version {current_version}")
        self.incident_id = incident_id
        self.current_version = current_version


class InvalidTransition(Exception):
    pass
