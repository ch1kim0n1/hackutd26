"""GLUE-02: correlation -> queue -> tool worker -> grounded report."""
import pytest

from correlation_agent import (
    CorrelationEngine,
    EvidenceStore,
    InvestigationError,
    InvestigationPipeline,
    ToolWorker,
)


def backends():
    return {
        "inventory_lookup": lambda a: {"asset": "srv-01",
                                       "evidence_ids": ["inv-1"]},
        "sensor_recent": lambda a: {"readings": 12,
                                    "evidence_ids": ["sns-1"]},
        "zone_assets": lambda a: {"assets": ["srv-01", "sw-02"],
                                  "evidence_ids": ["zone-1"]},
        "rf_context": lambda a: {"aps": 3, "evidence_ids": ["rf-1"]},
        "mission_status": lambda a: {"state": "idle"},
    }


@pytest.fixture
def rig():
    corr = CorrelationEngine()
    ev = EvidenceStore()
    for eid in ("ev-rf", "ev-door", "inv-1", "sns-1", "zone-1", "rf-1"):
        ev.add(eid, "observation", {"id": eid})
    pipe = InvestigationPipeline(corr, ToolWorker(backends()), ev)
    return corr, pipe


def candidate(corr):
    corr.observe("wifi_ap_seen", "rack-01", "ev-rf")
    return corr.observe("cabinet_open", "rack-01", "ev-door")


def script3():
    return [("inventory_lookup", {"asset": "srv-01"}),
            ("sensor_recent", {"zone": "rack-01"}),
            ("rf_context", {"zone": "rack-01"})]


def test_correlation_to_report(rig):
    corr, pipe = rig
    cand = candidate(corr)
    assert cand is not None and cand.rule == "CORR01"
    pipe.enqueue(cand)
    rep = pipe.investigate(
        cand, script3(),
        findings=["rogue AP correlates with cabinet access ev-rf"],
        unknowns=["whether AP is attacker or misconfigured"],
        alternates=["authorized contractor device"],
        proposals=[{"action": "isolate_ap", "status": "proposed_only"}])
    assert rep.tool_calls == 3
    assert "ev-rf" in rep.citations and "inv-1" in rep.citations
    assert rep.unknowns and rep.alternate_explanations
    assert all(t.startswith("tr-") for t in rep.trace_ids)


def test_too_few_tool_calls_rejected(rig):
    corr, pipe = rig
    cand = candidate(corr)
    with pytest.raises(InvestigationError):
        pipe.investigate(cand, [("inventory_lookup", {})],
                         findings=["x"], unknowns=["u"],
                         alternates=["a"])


def test_uncited_report_rejected(rig):
    corr, pipe = rig
    cand = candidate(corr)
    # all tools return evidence ids NOT in store -> no verifiable cites
    ghost = lambda a: {"evidence_ids": [f"ghost-{a}"]}
    w = ToolWorker({"inventory_lookup": ghost, "sensor_recent": ghost,
                    "rf_context": ghost})
    pipe2 = InvestigationPipeline(corr, w, EvidenceStore())
    with pytest.raises(InvestigationError, match="citations"):
        pipe2.investigate(cand, script3()[:3], findings=["f"],
                          unknowns=["u"], alternates=["a"])


def test_missing_unknowns_or_alternates_rejected(rig):
    corr, pipe = rig
    cand = candidate(corr)
    with pytest.raises(InvestigationError, match="unknowns"):
        pipe.investigate(cand, script3(), findings=["f"], unknowns=[],
                         alternates=["a"])
    with pytest.raises(InvestigationError, match="alternate"):
        pipe.investigate(cand, script3(), findings=["f"],
                         unknowns=["u"], alternates=[])


def test_unapproved_containment_is_proposal_only(rig):
    corr, pipe = rig
    cand = candidate(corr)
    rep = pipe.investigate(
        cand, script3(), findings=["f"], unknowns=["u"],
        alternates=["a"],
        proposals=[{"action": "isolate_endpoint", "needs": "approval"}])
    # proposals recorded but never executed — no executor exists here
    assert rep.containment_proposals[0]["needs"] == "approval"
    assert not hasattr(pipe, "execute")


def test_tool_allowlist_enforced(rig):
    corr, pipe = rig
    cand = candidate(corr)
    with pytest.raises(InvestigationError):
        pipe.worker.call("shell_exec", {}, "tr-x")
