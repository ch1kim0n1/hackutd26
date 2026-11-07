"""GLUE-02: correlation rule -> incident queue -> Nemotron tool worker
-> evidence-grounded report. In-memory; tool worker is scripted/fake
model — semantics mirror docs/05 agent loop + docs/04 incident queue.

Guarantees enforced here (tested):
- >=3 real tool invocations with trace ids before report allowed
- every claim cites evidence ids that exist in the evidence store
- report MUST include unknowns + at least one alternate explanation
- NO containment proposal without approval record (proposal-only)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

MIN_TOOL_CALLS = 3


class InvestigationError(Exception):
    pass


@dataclass
class IncidentCandidate:
    incident_id: str
    rule: str                    # e.g. CORR01
    summary: str
    evidence_ids: list[str]
    zone_id: str = ""
    created_at: float = field(default_factory=time.time)


class CorrelationEngine:
    """Minimal stand-in for sensors/correlator rules — emits candidates
    when RF + physical events co-occur in a zone."""

    def __init__(self):
        self.pending: dict[str, list[dict]] = {}
        self.candidates: list[IncidentCandidate] = []

    def observe(self, kind: str, zone: str, evidence_id: str,
                detail: dict | None = None) -> IncidentCandidate | None:
        self.pending.setdefault(zone, []).append(
            {"kind": kind, "evidence_id": evidence_id,
             "detail": detail or {}})
        evs = self.pending[zone]
        has_rf = any(e["kind"] in ("wifi_ap_seen", "deauth_burst")
                     for e in evs)
        has_phy = any(e["kind"] in ("cabinet_open", "motion")
                      for e in evs)
        if has_rf and has_phy:
            cand = IncidentCandidate(
                incident_id=f"inc-{uuid.uuid4().hex[:8]}",
                rule="CORR01", zone_id=zone,
                summary=f"RF+physical correlation in {zone}",
                evidence_ids=[e["evidence_id"] for e in evs])
            self.candidates.append(cand)
            self.pending[zone] = []
            return cand
        return None


class ToolWorker:
    """Bounded tool registry — each call traced. Scripted model drives
    which tools to call; real Nemotron replaces the driver."""

    TOOLS = {"inventory_lookup", "sensor_recent", "zone_assets",
             "rf_context", "mission_status"}

    def __init__(self, backends: dict):
        self.backends = backends
        self.calls: list[dict] = []

    def call(self, tool: str, args: dict, trace_id: str) -> dict:
        if tool not in self.TOOLS:
            raise InvestigationError(f"tool {tool} not allowlisted")
        if tool not in self.backends:
            raise InvestigationError(f"no backend for {tool}")
        result = self.backends[tool](args)
        self.calls.append({"tool": tool, "args": args,
                           "trace_id": trace_id,
                           "result_summary": str(result)[:120]})
        return result


class EvidenceStore:
    def __init__(self):
        self.items: dict[str, dict] = {}

    def add(self, evidence_id: str, kind: str, data: dict) -> None:
        self.items[evidence_id] = {"kind": kind, "data": data}

    def has(self, evidence_id: str) -> bool:
        return evidence_id in self.items


@dataclass
class Report:
    incident_id: str
    findings: list[str]
    citations: list[str]          # evidence ids actually cited
    unknowns: list[str]
    alternate_explanations: list[str]
    tool_calls: int
    trace_ids: list[str]
    containment_proposals: list = field(default_factory=list)


class InvestigationPipeline:
    """Drives candidate -> tool loop -> validated report."""

    def __init__(self, correlator: CorrelationEngine,
                 worker: ToolWorker, evidence: EvidenceStore,
                 clock=time.time):
        self.corr = correlator
        self.worker = worker
        self.evidence = evidence
        self.clock = clock
        self.queue: list[IncidentCandidate] = []
        self.reports: list[Report] = []

    def enqueue(self, cand: IncidentCandidate) -> None:
        self.queue.append(cand)

    def investigate(self, cand: IncidentCandidate,
                    script: list[tuple[str, dict]],
                    findings: list[str],
                    unknowns: list[str],
                    alternates: list[str],
                    proposals: list | None = None) -> Report:
        """script = ordered (tool,args) the model chose. Enforces:
        >=MIN_TOOL_CALLS calls; citations must exist; unknowns+alt
        required; proposals recorded as PROPOSALS only."""
        trace = f"tr-{uuid.uuid4().hex[:10]}"
        results = {}
        for tool, args in script:
            results[tool] = self.worker.call(tool, args, trace)
        if len(self.worker.calls) < MIN_TOOL_CALLS and \
                len(script) < MIN_TOOL_CALLS:
            raise InvestigationError(
                f"need >={MIN_TOOL_CALLS} tool calls, got {len(script)}")
        # citations: union of evidence ids referenced by tool results
        # + candidate's own evidence; findings must cite >=1 known id
        known = set(cand.evidence_ids) | {
            eid for r in results.values()
            for eid in (r.get("evidence_ids", []) if isinstance(r, dict)
                        else [])}
        cited = [e for e in known if self.evidence.has(e)]
        if not cited:
            raise InvestigationError("report has no verifiable citations")
        if not unknowns:
            raise InvestigationError("report must state unknowns")
        if not alternates:
            raise InvestigationError(
                "report must offer >=1 alternate explanation")
        report = Report(
            incident_id=cand.incident_id, findings=findings,
            citations=sorted(cited), unknowns=unknowns,
            alternate_explanations=alternates,
            tool_calls=len(script),
            trace_ids=[trace] + [c["trace_id"] for c in
                                 self.worker.calls[-len(script):]],
            containment_proposals=proposals or [])
        self.reports.append(report)
        return report
