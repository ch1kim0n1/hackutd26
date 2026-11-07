"""Scope matrix model — docs/06 R04, `scope_entries` contract docs/04.

Per-asset/per-dataset compromise scope. Confidentiality, integrity and
availability tracked INDEPENDENTLY. `unknown` is a first-class status —
it must never be silently treated as `unaffected`."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class ScopeStatus(str, Enum):
    UNKNOWN = "unknown"
    SUSPECTED_EXPOSED = "suspected_exposed"
    CONFIRMED_EXPOSED = "confirmed_exposed"
    EXFILTRATED = "exfiltrated"
    ENCRYPTED_LOCKED = "encrypted_locked"
    CORRUPTED = "corrupted"
    UNAVAILABLE = "unavailable"
    CONTAINED = "contained"
    RESTORED = "restored"
    UNAFFECTED = "unaffected"


# statuses implying confirmed compromise (need strong evidence)
CONFIRMED = {ScopeStatus.CONFIRMED_EXPOSED, ScopeStatus.EXFILTRATED,
             ScopeStatus.ENCRYPTED_LOCKED, ScopeStatus.CORRUPTED}
# statuses implying suspected-only
SUSPECTED = {ScopeStatus.SUSPECTED_EXPOSED, ScopeStatus.UNKNOWN}


class CIA(str, Enum):
    CONFIDENTIALITY = "confidentiality"
    INTEGRITY = "integrity"
    AVAILABILITY = "availability"


# which CIA dimension each status primarily impacts (others may also)
STATUS_CIA: dict[ScopeStatus, set[CIA]] = {
    ScopeStatus.UNKNOWN: set(),
    ScopeStatus.SUSPECTED_EXPOSED: {CIA.CONFIDENTIALITY},
    ScopeStatus.CONFIRMED_EXPOSED: {CIA.CONFIDENTIALITY},
    ScopeStatus.EXFILTRATED: {CIA.CONFIDENTIALITY},
    ScopeStatus.ENCRYPTED_LOCKED: {CIA.AVAILABILITY, CIA.CONFIDENTIALITY},
    ScopeStatus.CORRUPTED: {CIA.INTEGRITY},
    ScopeStatus.UNAVAILABLE: {CIA.AVAILABILITY},
    ScopeStatus.CONTAINED: set(),
    ScopeStatus.RESTORED: set(),
    ScopeStatus.UNAFFECTED: set(),
}

# evidence kinds strong enough to assert a CONFIRMED status
STRONG_EVIDENCE = {"edr_alert", "auth_log", "file_sample", "ransom_note",
                   "exfil_capture", "backup_diff", "manual_verified"}
# weak/suspected-only evidence — RF/AP anomalies can NEVER confirm breach
WEAK_EVIDENCE = {"rf_frame", "wifi_ap", "ble_event", "motion", "door",
                 "camera", "observation", "chat"}


@dataclass
class ScopeEntry:
    entry_id: str
    incident_id: str
    asset_id: str
    dataset: str = ""               # e.g. "file-share", "db-customers"
    cia: dict[CIA, ScopeStatus] = field(default_factory=dict)
    record_count_estimate: int | None = None
    impact_window_start: float | None = None
    impact_window_end: float | None = None
    evidence_refs: list[str] = field(default_factory=list)
    reviewer_id: str = ""
    notes: str = ""
    version: int = 1
    updated_at: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        for c in CIA:
            self.cia.setdefault(c, ScopeStatus.UNKNOWN)

    def status_summary(self) -> dict[str, str]:
        return {c.value: s.value for c, s in self.cia.items()}


@dataclass
class ScopeSnapshot:
    """Immutable point-in-time copy — earlier snapshots stay in audit
    history (W04e)."""
    seq: int
    at: float
    by: str
    reason: str
    entries: dict[str, dict]   # entry_id -> {asset,dataset,cia,...}


class ScopeError(Exception):
    pass


class InsufficientEvidence(ScopeError):
    """Attempted CONFIRMED status with only weak/suspected evidence —
    e.g. an RF/AP event can never prove data exfiltration."""
    pass


class VersionConflict(ScopeError):
    def __init__(self, entry_id: str, current: int):
        super().__init__(f"{entry_id} at version {current}")
        self.current = current
