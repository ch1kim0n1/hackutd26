from defense_gateway import (
    DecisionEngine,
    FlowDecisionKind,
    FlowEndpoint,
    FlowMatch,
    FlowPolicy,
    FlowRule,
    FlowTuple,
    SimulatedEnforcementPoint,
)

DECOY = FlowEndpoint("rover-decoy-01", "http")


def policy() -> FlowPolicy:
    return FlowPolicy(policy_id="pol-enf", rules=[
        FlowRule("r-redir", FlowMatch(dst_service="ssh"),
                 FlowDecisionKind.REDIRECT, redirect_to=DECOY),
        FlowRule("r-block", FlowMatch(dst_service="telnet"),
                 FlowDecisionKind.BLOCK),
    ])


def decide(service, now=1_700_000_000):
    f = FlowTuple(flow_id=f"flow-{service}",
                  src=FlowEndpoint("lab-client-01", "https"),
                  dst=FlowEndpoint("dc-pi-01", service))
    return DecisionEngine(policy()).evaluate(f, trace_id="t-enf", now=now)


def test_allow_block_redirect_outcomes():
    ep = SimulatedEnforcementPoint()
    # unmatched under default DENY -> block
    assert ep.apply(decide("https")).result == "block"
    b = ep.apply(decide("telnet"))
    assert b.result == "block" and b.redirect_target is None
    r = ep.apply(decide("ssh"))
    assert r.result == "redirect"
    assert r.redirect_target == "rover-decoy-01/http"


def test_outcome_always_simulated_and_correlated():
    ep = SimulatedEnforcementPoint()
    d = decide("ssh")
    o = ep.apply(d, now=1_700_000_100)
    rec = o.as_record()
    assert rec["enforcement"] == "simulated"
    assert rec["decision_id"] == d.decision_id
    assert rec["flow_id"] == d.flow.flow_id
    assert rec["trace_id"] == "t-enf"
    assert rec["schema_version"] == 1
    assert rec["at"].endswith("Z")


def test_enforcement_does_not_mutate_decision():
    d = decide("ssh")
    before = d.as_record()
    SimulatedEnforcementPoint().apply(d)
    assert d.as_record() == before  # decision record untouched


def test_apply_rejects_non_decision():
    import pytest
    with pytest.raises(TypeError):
        SimulatedEnforcementPoint().apply({"decision": "allow"})
