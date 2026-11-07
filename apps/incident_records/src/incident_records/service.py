"""IncidentService — records, versioned edits, state machine,
timeline, evidence links, packet export (docs/06 R03, docs/04)."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict

from .models import (
    Incident,
    EvidenceRef,
    IncidentState,
    Severity,
    TimelineEvent,
    TRANSITIONS,
    InvalidTransition,
    VersionConflict,
)


def _ts(clock) -> float:
    return clock()


class IncidentService:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.incidents: dict[str, Incident] = {}

    # ---------------- lifecycle ----------------
    def create(self, actor_id: str, title: str, summary: str = "",
               severity: Severity = Severity.MEDIUM, zone_id: str = "",
               provenance: dict | None = None) -> Incident:
        inc = Incident(incident_id=f"inc-{uuid.uuid4().hex[:10]}",
                       title=title, summary=summary, severity=severity,
                       zone_id=zone_id, created_by=actor_id,
                       provenance=provenance or {})
        inc.timeline.append(TimelineEvent(
            seq=1, at=_ts(self.clock), actor_id=actor_id, kind="created",
            detail={"title": title, "severity": severity.value}))
        self.incidents[inc.incident_id] = inc
        return inc

    def get(self, incident_id: str) -> Incident:
        return self.incidents[incident_id]

    # ---------------- versioned edits ----------------
    def update(self, incident_id: str, actor_id: str,
               expected_version: int, fields: dict) -> Incident:
        """Optimistic concurrency: caller MUST supply the version it
        read. Stale version -> VersionConflict (visible to user, never
        silent overwrite). Bumps version + timeline on success."""
        inc = self.get(incident_id)
        if inc.version != expected_version:
            raise VersionConflict(incident_id, inc.version)
        bad = set(fields) - Incident.EDITABLE
        if bad:
            raise ValueError(f"non-editable fields: {sorted(bad)}")
        for k, v in fields.items():
            if k == "confidence":
                v = max(0.0, min(1.0, float(v)))
            setattr(inc, k, v)
        inc.version += 1
        inc.updated_at = _ts(self.clock)
        self._tl(inc, actor_id, "field_edit",
                 {"fields": fields, "version": inc.version})
        return inc

    def transition(self, incident_id: str, actor_id: str,
                   to_state: IncidentState, expected_version: int,
                   reason: str = "") -> Incident:
        inc = self.get(incident_id)
        if inc.version != expected_version:
            raise VersionConflict(incident_id, inc.version)
        allowed = TRANSITIONS.get(inc.state, set())
        if to_state not in allowed:
            raise InvalidTransition(
                f"{inc.state.value} -> {to_state.value} not allowed")
        frm = inc.state
        inc.state = to_state
        inc.version += 1
        inc.updated_at = _ts(self.clock)
        self._tl(inc, actor_id, "state_change",
                 {"from": frm.value, "to": to_state.value,
                  "reason": reason, "version": inc.version})
        return inc

    def assign(self, incident_id: str, actor_id: str,
               owner_id: str, expected_version: int) -> Incident:
        return self.update(incident_id, actor_id, expected_version,
                           {"owner_id": owner_id})

    def add_note(self, incident_id: str, actor_id: str, text: str) -> Incident:
        inc = self.get(incident_id)
        inc.notes.append({"at": _ts(self.clock), "by": actor_id,
                          "text": text})
        self._tl(inc, actor_id, "note", {"text": text[:200]})
        return inc

    # ---------------- evidence ----------------
    def link_evidence(self, incident_id: str, actor_id: str,
                      evidence_id: str, kind: str,
                      note: str = "") -> Incident:
        inc = self.get(incident_id)
        inc.evidence.append(EvidenceRef(
            evidence_id=evidence_id, kind=kind, note=note,
            added_by=actor_id))
        inc.version += 1
        inc.updated_at = _ts(self.clock)
        self._tl(inc, actor_id, "evidence_add",
                 {"evidence_id": evidence_id, "kind": kind})
        return inc

    def _tl(self, inc: Incident, actor: str, kind: str,
            detail: dict) -> None:
        inc.timeline.append(TimelineEvent(
            seq=len(inc.timeline) + 1, at=_ts(self.clock),
            actor_id=actor, kind=kind, detail=detail))

    # ---------------- export ----------------
    def export_packet(self, incident_id: str, actor_id: str) -> dict:
        """Standards-inspired incident packet: full record + timeline +
        evidence + provenance, export event recorded in timeline."""
        inc = self.get(incident_id)
        packet = {
            "packet_version": 1,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                         time.gmtime(_ts(self.clock))),
            "exported_by": actor_id,
            "incident": {
                "incident_id": inc.incident_id,
                "title": inc.title,
                "summary": inc.summary,
                "state": inc.state.value,
                "severity": inc.severity.value,
                "confidence": inc.confidence,
                "owner_id": inc.owner_id,
                "zone_id": inc.zone_id,
                "created_by": inc.created_by,
                "created_at": inc.created_at,
                "updated_at": inc.updated_at,
                "version": inc.version,
                "provenance": inc.provenance,
            },
            "evidence": [asdict(e) for e in inc.evidence],
            "timeline": [asdict(t) for t in inc.timeline],
            "notes": inc.notes,
        }
        self._tl(inc, actor_id, "export", {"packet_bytes": len(
            json.dumps(packet))})
        return packet

    def export_markdown(self, incident_id: str, actor_id: str) -> str:
        p = self.export_packet(incident_id, actor_id)
        i = p["incident"]
        lines = [
            f"# Incident {i['incident_id']}: {i['title']}",
            "",
            f"- state: `{i['state']}`  severity: `{i['severity']}`"
            f"  confidence: {i['confidence']:.2f}",
            f"- owner: `{i['owner_id'] or 'unassigned'}`  zone:"
            f" `{i['zone_id'] or '-'}`",
            f"- created: {i['created_at']:.0f} by `{i['created_by']}`"
            f"  updated: {i['updated_at']:.0f} v{i['version']}",
            "",
            "## Summary", "", i["summary"] or "_none_", "",
            "## Evidence", ""]
        for e in p["evidence"]:
            lines.append(f"- `{e['evidence_id']}` ({e['kind']})"
                         + (f" — {e['note']}" if e["note"] else ""))
        if not p["evidence"]:
            lines.append("_none_")
        lines += ["", "## Timeline", ""]
        for t in p["timeline"]:
            lines.append(f"- `{t['at']:.0f}` **{t['actor_id']}**"
                         f" {t['kind']}: `{json.dumps(t['detail'])[:120]}`")
        lines += ["", "## Notes", ""]
        for n in p["notes"]:
            lines.append(f"- `{n['at']:.0f}` **{n['by']}**: {n['text']}")
        if not p["notes"]:
            lines.append("_none_")
        return "\n".join(lines)
