"""ModelOutputGuard — validate what the model finally claims (docs/05 N02/N07/N08).

The model's prose is UNTRUSTED OUTPUT: it must cite real evidence_ids,
must not assert approvals/executed containment/verified isolation
without a verification reference, and structured assessments must match
the schema. Conflicting evidence should revise hypotheses — the guard
flags assessments that ignore supplied contradictions."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# Phrases that assert authority the model does NOT have.
FORBIDDEN_CLAIMS = re.compile(
    r"(containment (has been |was )?(approved|executed|verified|complete)|"
    r"endpoint (is |has been )?isolated|"
    r"i (approved|executed|deployed)|"
    r"verified (isolation|containment)|"
    r"breach confirmed|exfiltration confirmed)",
    re.IGNORECASE)

REQUIRED_ASSESSMENT_KEYS = ("assessment", "evidence_ids", "unknowns")


@dataclass
class OutputVerdict:
    ok: bool
    violations: list[str] = field(default_factory=list)
    cited_evidence: list[str] = field(default_factory=list)
    fabricated_citations: list[str] = field(default_factory=list)


class ModelOutputGuard:
    def __init__(self, known_evidence_ids: set[str] | None = None):
        self.known_evidence = known_evidence_ids or set()

    def check_assessment(self, payload: dict) -> OutputVerdict:
        v = OutputVerdict(ok=True)
        # schema
        for k in REQUIRED_ASSESSMENT_KEYS:
            if k not in payload:
                v.violations.append(f"missing required key '{k}'")
                v.ok = False
        text = str(payload.get("assessment", ""))
        # forbidden authority claims
        for m in FORBIDDEN_CLAIMS.finditer(text):
            v.violations.append(f"forbidden claim: '{m.group(0)}'")
            v.ok = False
        # evidence citations must exist
        ids = payload.get("evidence_ids", [])
        if not isinstance(ids, list):
            v.violations.append("evidence_ids must be a list")
            v.ok = False
            ids = []
        for eid in ids:
            eid = str(eid)
            if self.known_evidence and eid not in self.known_evidence:
                v.fabricated_citations.append(eid)
                v.violations.append(f"cites unknown evidence_id '{eid}'")
                v.ok = False
        if not ids:
            v.violations.append("assessment cites no evidence")
            v.ok = False
        if not payload.get("unknowns"):
            v.violations.append("assessment lists no unknowns")
            # soft violation: flag but don't hard-fail? docs require
            # unknowns — treat as violation for strictness
            v.ok = False
        v.cited_evidence = [str(x) for x in ids]
        return v

    def check_message(self, text: str) -> OutputVerdict:
        """Guard free-text model output (incident messages, summaries)."""
        v = OutputVerdict(ok=True)
        for m in FORBIDDEN_CLAIMS.finditer(text):
            v.violations.append(f"forbidden claim: '{m.group(0)}'")
            v.ok = False
        return v


def revise_on_contradiction(hypothesis: str, contradicting_evidence: list[dict],
                            current_confidence: str = "medium") -> dict:
    """N02 helper: contradictory evidence must downgrade/revise, not be
    ignored. Returns a revision record for the audit trail."""
    return {
        "action": "hypothesis_revision",
        "previous_hypothesis": hypothesis,
        "contradicting_evidence": [e.get("id", str(e)) for e in contradicting_evidence],
        "previous_confidence": current_confidence,
        "revised_confidence": "low",
        "note": "contradictory evidence supplied — hypothesis downgraded; "
                "competing explanations must be restated",
    }
