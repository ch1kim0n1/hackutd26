"""ScopeMatrix service — per-asset/dataset CIA status, evidence-gated
transitions, versioned snapshots, audit (docs/06 R04, docs/04
`scope_entries`)."""
from __future__ import annotations

import time
from dataclasses import asdict

from .models import (
    CIA,
    CONFIRMED,
    STRONG_EVIDENCE,
    WEAK_EVIDENCE,
    ScopeEntry,
    ScopeSnapshot,
    ScopeStatus,
    InsufficientEvidence,
    VersionConflict,
)


class ScopeMatrix:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.entries: dict[str, ScopeEntry] = {}
        self.snapshots: list[ScopeSnapshot] = []
        self.audit: list[dict] = []

    # ---------------- CRUD ----------------
    def add_entry(self, incident_id: str, asset_id: str,
                  dataset: str = "", by: str = "") -> ScopeEntry:
        e = ScopeEntry(entry_id=f"scope-{len(self.entries)+1:04d}",
                       incident_id=incident_id, asset_id=asset_id,
                       dataset=dataset, reviewer_id=by)
        self.entries[e.entry_id] = e
        self._audit(by, "entry_add", e.entry_id,
                    {"asset": asset_id, "dataset": dataset})
        return e

    def get(self, entry_id: str) -> ScopeEntry:
        return self.entries[entry_id]

    def entries_for_incident(self, incident_id: str) -> list[ScopeEntry]:
        return [e for e in self.entries.values()
                if e.incident_id == incident_id]

    # ---------------- status updates ----------------
    def set_status(self, entry_id: str, by: str, expected_version: int,
                   cia: CIA, status: ScopeStatus,
                   evidence_kind: str | None = None,
                   evidence_ref: str | None = None,
                   reason: str = "") -> ScopeEntry:
        """Update ONE CIA dimension. CONFIRMED statuses require strong
        evidence — weak RF/AP/observation evidence can only justify
        suspected/unknown, never confirmed_exposed/exfiltrated."""
        e = self.get(entry_id)
        if e.version != expected_version:
            raise VersionConflict(entry_id, e.version)
        # evidence gate
        if status in CONFIRMED:
            if evidence_kind not in STRONG_EVIDENCE:
                raise InsufficientEvidence(
                    f"{status.value} requires strong evidence "
                    f"({sorted(STRONG_EVIDENCE)}); got {evidence_kind!r} — "
                    f"RF/AP/observation anomalies cannot confirm breach")
        elif evidence_kind in WEAK_EVIDENCE and \
                status in (ScopeStatus.CONFIRMED_EXPOSED,
                           ScopeStatus.EXFILTRATED):
            raise InsufficientEvidence("weak evidence cannot confirm")
        # apply
        old = e.cia[cia]
        e.cia[cia] = status
        e.version += 1
        e.updated_at = self.clock()
        if evidence_ref:
            e.evidence_refs.append(evidence_ref)
        self._audit(by, "status_change", entry_id,
                    {"cia": cia.value, "from": old.value,
                     "to": status.value, "evidence_kind": evidence_kind,
                     "evidence_ref": evidence_ref, "reason": reason,
                     "version": e.version})
        return e

    def set_impact(self, entry_id: str, by: str, expected_version: int,
                   record_count: int | None = None,
                   window_start: float | None = None,
                   window_end: float | None = None,
                   notes: str | None = None) -> ScopeEntry:
        e = self.get(entry_id)
        if e.version != expected_version:
            raise VersionConflict(entry_id, e.version)
        if record_count is not None:
            e.record_count_estimate = max(0, int(record_count))
        if window_start is not None:
            e.impact_window_start = window_start
        if window_end is not None:
            e.impact_window_end = window_end
        if notes is not None:
            e.notes = notes
        e.version += 1
        e.updated_at = self.clock()
        self._audit(by, "impact_update", entry_id,
                    {"records": e.record_count_estimate,
                     "window": [e.impact_window_start,
                                e.impact_window_end],
                     "version": e.version})
        return e

    def link_evidence(self, entry_id: str, by: str, evidence_ref: str) -> None:
        e = self.get(entry_id)
        e.evidence_refs.append(evidence_ref)
        self._audit(by, "evidence_link", entry_id,
                    {"ref": evidence_ref})

    # ---------------- snapshots ----------------
    def snapshot(self, by: str, reason: str = "") -> ScopeSnapshot:
        snap = ScopeSnapshot(
            seq=len(self.snapshots) + 1, at=self.clock(), by=by,
            reason=reason,
            entries={eid: {"asset_id": e.asset_id,
                           "dataset": e.dataset,
                           "cia": e.status_summary(),
                           "records": e.record_count_estimate,
                           "version": e.version}
                     for eid, e in self.entries.items()})
        self.snapshots.append(snap)
        self._audit(by, "snapshot", "*", {"seq": snap.seq,
                                          "reason": reason})
        return snap

    def snapshot_at(self, seq: int) -> ScopeSnapshot:
        return self.snapshots[seq - 1]

    def _audit(self, by: str, op: str, target: str, detail: dict) -> None:
        self.audit.append({"at": self.clock(), "by": by, "op": op,
                           "target": target, "detail": detail})
