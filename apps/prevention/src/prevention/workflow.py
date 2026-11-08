"""Preventive incident workflow (#103).

Converts ranked posture findings (risk_priority output dicts) into
prioritized incident CANDIDATES. These are posture weaknesses, NOT
attacks — candidates are labeled preventive and queue for human/agent
review. No containment execution, no attack claims.

Pipeline: findings -> dedup -> risk rank -> policy gate (auto-queue vs
hold) -> incident candidate with evidence bundle + Nemotron-ready
context. Deterministic ordering; unknowns stay unknown.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CandidateStatus(str, Enum):
    QUEUED = "queued"            # awaiting review/assignment
    AUTO_FILED = "auto_filed"    # policy allowed immediate filing
    HELD = "held"                # below policy threshold
    DISMISSED = "dismissed"      # duplicate/superseded


@dataclass
class IncidentCandidate:
    candidate_id: str
    node_ref: str
    check_id: str
    title: str
    severity: str
    confidence: str
    risk_score: float
    rank: int
    status: CandidateStatus
    provenance: str
    evidence_refs: list
    finding_ids: list
    context_bundle: dict = field(default_factory=dict)
    created_tick: int = 0

    def as_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "node_ref": self.node_ref,
            "check_id": self.check_id,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "rank": self.rank,
            "status": self.status.value,
            "kind": "preventive_posture",   # distinct from attack incidents
            "provenance": self.provenance,
            "evidence_refs": self.evidence_refs,
            "finding_ids": self.finding_ids,
            "context_bundle": self.context_bundle,
            "created_tick": self.created_tick,
        }


def _candidate_id(node_ref: str, check_id: str, detail_hash: str) -> str:
    blob = f"{node_ref}|{check_id}|{detail_hash}".encode()
    return "cand-" + hashlib.sha256(blob).hexdigest()[:12]


def _detail_hash(finding: dict) -> str:
    detail = finding.get("detail", {})
    return hashlib.sha256(
        json.dumps(detail, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]


def nemotron_context(candidate: "IncidentCandidate",
                     summary: str = "", detail: Optional[dict] = None) -> dict:
    """Structured, citable context bundle for agent assessment.
    Every claim traceable to evidence_refs; unknowns explicit."""
    detail = detail or {}
    return {
        "task": "assess_posture_finding",
        "candidate_id": candidate.candidate_id,
        "node": candidate.node_ref,
        "check": candidate.check_id,
        "severity": candidate.severity,
        "confidence": candidate.confidence,
        "provenance": candidate.provenance,
        "summary": summary or candidate.title,
        "risk_score": candidate.risk_score,
        "evidence_refs": candidate.evidence_refs,
        "unknowns": [k for k, v in detail.items()
                     if v in (None, "unknown", "")],
        "constraints": [
            "posture finding, not an attack",
            "recommend hardening action, do not claim prevention",
            "preserve unknown confidence",
        ],
    }


class PreventionPolicy:
    """Gate for auto-filing. Conservative defaults: only confirmed
    high/critical findings auto-file; everything else queues."""

    def __init__(self, auto_file_min_severity: str = "high",
                 auto_file_min_confidence: str = "confirmed"):
        self._sev = {"info": 0, "low": 1, "medium": 2, "high": 3,
                     "critical": 4}
        self._conf = {"unknown": 0, "suspected": 1, "confirmed": 2}
        self.auto_file_min_severity = auto_file_min_severity
        self.auto_file_min_confidence = auto_file_min_confidence

    def allows_auto_file(self, candidate: IncidentCandidate) -> bool:
        return (self._sev.get(candidate.severity, 0)
                >= self._sev[self.auto_file_min_severity]
                and self._conf.get(candidate.confidence, 0)
                >= self._conf[self.auto_file_min_confidence])


def build_candidates(ranked: list[dict],
                     policy: Optional[PreventionPolicy] = None,
                     tick: int = 0) -> list[dict]:
    """ranked = risk_priority.prioritize() output. Returns candidate dicts."""
    policy = policy or PreventionPolicy()
    out: list[IncidentCandidate] = []
    seen: dict[str, IncidentCandidate] = {}

    for r in ranked:
        fid = r.get("finding_id", "")
        node = r.get("node_ref", "")
        check = r.get("check_id", "")
        cid = _candidate_id(node, check, fid)
        if cid in seen:
            # merge evidence refs, keep higher rank
            c = seen[cid]
            c.evidence_refs = sorted(set(c.evidence_refs
                                         + r.get("evidence_refs", [])))
            c.finding_ids.append(fid)
            continue
        sev = r.get("severity", "info")
        conf = r.get("confidence", "unknown")
        title = (f"Posture: {check} on {node} "
                 f"({sev}/{conf})")
        cand = IncidentCandidate(
            candidate_id=cid, node_ref=node, check_id=check,
            title=title, severity=sev, confidence=conf,
            risk_score=r.get("score", 0.0), rank=r.get("rank", 0),
            status=(CandidateStatus.QUEUED),
            provenance=r.get("provenance", "DEMO"),
            evidence_refs=list(r.get("evidence_refs", [])),
            finding_ids=[fid], created_tick=tick,
        )
        cand.context_bundle = nemotron_context(cand)
        seen[cid] = cand
        out.append(cand)

    # policy gate after dedup
    for c in out:
        if policy.allows_auto_file(c):
            c.status = CandidateStatus.AUTO_FILED
        elif c.severity in ("info", "low") and c.confidence == "unknown":
            c.status = CandidateStatus.HELD

    out.sort(key=lambda c: (c.rank, c.candidate_id))
    return [c.as_dict() for c in out]
