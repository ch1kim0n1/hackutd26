"""Risk prioritization engine (#127).

Turns posture findings (apps/posture Finding dicts) into a ranked queue:
risk_score = severity_weight x exposure x asset_criticality.
Deterministic ordering + human-readable explanation per rank. Dedup of
repeat findings. Output contract consumable by apps/incident_records.

No incident creation, no UI, no containment proposals, no live data.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional

# severity -> numeric weight (aligns with posture Severity enum values)
SEVERITY_WEIGHT = {
    "critical": 8.0,
    "high": 5.0,
    "medium": 2.5,
    "low": 1.0,
    "info": 0.25,
}
CONFIDENCE_FACTOR = {
    "confirmed": 1.0,
    "suspected": 0.6,
    "unknown": 0.2,
}

# zone -> exposure multiplier (restricted zone = higher blast radius)
ZONE_EXPOSURE = {
    "rack-01": 1.5,      # restricted customer row
    "lab-b": 1.0,        # staff network lab
    "lobby": 0.7,        # public ingress
    "bench-row": 0.5,    # workstations
}
DEFAULT_EXPOSURE = 1.0

# node_id prefix/role hints -> asset criticality
CRITICAL_NODES = {"vpi-mgmt-01": 2.0, "vpi-network-01": 1.8,
                  "vpi-compute-01": 1.5, "vpi-sensor-01": 1.0}
DEFAULT_CRITICALITY = 1.0


def _stable_id(f: dict) -> str:
    """Dedup key: same check+node+detail = same finding."""
    blob = f"{f.get('check_id')}|{f.get('node_ref')}|{f.get('detail')}"
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def exposure_for(f: dict, zone_map: Optional[dict] = None) -> float:
    """Finding's exposure: zone lookup, then detail fallbacks."""
    zm = zone_map or ZONE_EXPOSURE
    zone = f.get("zone_id") or f.get("detail", {}).get("zone_id")
    if zone and zone in zm:
        return zm[zone]
    node = f.get("node_ref", "")
    for z, v in zm.items():
        if z in node:
            return v
    return DEFAULT_EXPOSURE


def criticality_for(node_ref: str) -> float:
    return CRITICAL_NODES.get(node_ref, DEFAULT_CRITICALITY)


@dataclass
class RankedItem:
    rank: int
    finding_id: str
    node_ref: str
    check_id: str
    severity: str
    confidence: str
    score: float
    explanation: str
    finding: dict = field(repr=False)

    def as_dict(self) -> dict:
        """Contract consumable by apps/incident_records later."""
        return {
            "rank": self.rank,
            "finding_id": self.finding_id,
            "node_ref": self.node_ref,
            "check_id": self.check_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "score": round(self.score, 4),
            "explanation": self.explanation,
            "provenance": self.finding.get("provenance"),
            "evidence_refs": self.finding.get("evidence_refs", []),
        }


def score_finding(f: dict, zone_map: Optional[dict] = None) -> tuple[float, str]:
    """score + human explanation. Deterministic."""
    sev = SEVERITY_WEIGHT.get(f.get("severity", "info"), 0.25)
    conf = CONFIDENCE_FACTOR.get(f.get("confidence", "unknown"), 0.2)
    exp = exposure_for(f, zone_map)
    crit = criticality_for(f.get("node_ref", ""))
    score = sev * conf * exp * crit
    parts = [
        f"severity={f.get('severity')}({sev})",
        f"confidence={f.get('confidence')}({conf})",
        f"exposure={exp}",
        f"criticality={crit}",
    ]
    return score, "x".join(parts) + f" = {score:.2f}"


def prioritize(findings: list[dict],
               zone_map: Optional[dict] = None) -> list[dict]:
    """Dedup + rank findings. Returns list of contract dicts."""
    seen: dict[str, dict] = {}
    for f in findings:
        fid = _stable_id(f)
        # keep the highest-confidence variant of a duplicate
        if fid not in seen or CONFIDENCE_FACTOR.get(
                f.get("confidence", ""), 0) > CONFIDENCE_FACTOR.get(
                seen[fid].get("confidence", ""), 0):
            seen[fid] = f

    scored = []
    for fid, f in seen.items():
        score, expl = score_finding(f, zone_map)
        scored.append(RankedItem(
            rank=0, finding_id=fid,
            node_ref=f.get("node_ref", ""),
            check_id=f.get("check_id", ""),
            severity=f.get("severity", "info"),
            confidence=f.get("confidence", "unknown"),
            score=score, explanation=expl, finding=f,
        ))

    # stable order: score desc, then node_ref, check_id, finding_id
    scored.sort(key=lambda r: (-r.score, r.node_ref, r.check_id, r.finding_id))
    for i, r in enumerate(scored, 1):
        r.rank = i
    return [r.as_dict() for r in scored]
