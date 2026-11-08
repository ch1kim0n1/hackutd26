import pytest

from defense_gateway import (
    DecisionEngine,
    DefaultAction,
    FlowDecisionKind,
    FlowEndpoint,
    FlowMatch,
    FlowPolicy,
    FlowRule,
    FlowTuple,
    FlowValidationError,
    Provenance,
)

DECOY = FlowEndpoint("rover-decoy-01", "http")
PROTECTED = FlowEndpoint("dc-pi-02", "http")
CLIENT = FlowEndpoint("lab-client-01", "https")


def demo_policy(default=DefaultAction.DENY) -> FlowPolicy:
    return FlowPolicy(
        policy_id="pol-edge-01",
        version=3,
        default_action=default,
        default_ttl_s=45.0,
        rules=[
            FlowRule(
                rule_id="allow-lab-http",
                match=FlowMatch(src_node="lab-client-01",
                                dst_service="http"),
                action=FlowDecisionKind.ALLOW,
                reason="authorized lab client to protected http",
            ),
            FlowRule(
                rule_id="block-known-bad",
                match=FlowMatch(src_node="bad-actor-01"),
                action=FlowDecisionKind.BLOCK,
                reason="deny listed hostile lab source",
                ttl_s=30.0,
            ),
            FlowRule(
                rule_id="redirect-scan-to-decoy",
                match=FlowMatch(dst_service="ssh"),
                action=FlowDecisionKind.REDIRECT,
                redirect_to=DECOY,
                reason="route ssh probes to rover decoy",
            ),
        ],
    )


def flow(**kw) -> FlowTuple:
    args = dict(
        flow_id="flow-001",
        src=CLIENT,
        dst=PROTECTED,
        provenance=Provenance.DEMO,
    )
    args.update(kw)
    return FlowTuple(**args)


# ---------- allow / block / redirect ----------

def test_allow_rule_match():
    d = DecisionEngine(demo_policy()).evaluate(flow(), trace_id="t-1", now=1_700_000_000)
    assert d.decision is FlowDecisionKind.ALLOW
    assert d.rule_id == "allow-lab-http"
    assert d.matched is True
    assert d.policy_id == "pol-edge-01"
    assert d.policy_version == 3
    assert d.redirect_to is None


def test_block_rule_match():
    d = DecisionEngine(demo_policy()).evaluate(
        flow(flow_id="flow-002", src=FlowEndpoint("bad-actor-01", "https")),
        now=1_700_000_000)
    assert d.decision is FlowDecisionKind.BLOCK
    assert d.rule_id == "block-known-bad"
    assert d.ttl_s == 30.0  # rule TTL overrides policy default


def test_redirect_rule_match():
    d = DecisionEngine(demo_policy()).evaluate(
        flow(flow_id="flow-003", dst=FlowEndpoint("dc-pi-02", "ssh")),
        now=1_700_000_000)
    assert d.decision is FlowDecisionKind.REDIRECT
    assert d.rule_id == "redirect-scan-to-decoy"
    assert d.redirect_to == DECOY


def test_first_match_wins():
    # Overlapping rules: allow on dst_service=http is declared before
    # block on src_node=bad-actor-01; the flow matches both, so the
    # earlier rule must win.
    pol = FlowPolicy(policy_id="pol-order", rules=[
        FlowRule("r-allow", FlowMatch(dst_service="http"),
                 FlowDecisionKind.ALLOW),
        FlowRule("r-block", FlowMatch(src_node="bad-actor-01"),
                 FlowDecisionKind.BLOCK),
    ])
    d = DecisionEngine(pol).evaluate(
        flow(src=FlowEndpoint("bad-actor-01", "https")), now=1)
    assert d.decision is FlowDecisionKind.ALLOW and d.rule_id == "r-allow"


# ---------- default policy: explicit choice, tested ----------

def test_default_deny_unmatched():
    d = DecisionEngine(demo_policy(DefaultAction.DENY)).evaluate(
        flow(flow_id="flow-404", src=FlowEndpoint("unknown-01", "https"),
             dst=FlowEndpoint("dc-pi-09", "https")),
        now=1_700_000_000)
    assert d.decision is FlowDecisionKind.BLOCK
    assert d.rule_id is None and d.matched is False
    assert "default deny" in d.reason
    assert d.ttl_s == 45.0  # policy default TTL


def test_default_monitor_unmatched():
    d = DecisionEngine(demo_policy(DefaultAction.MONITOR)).evaluate(
        flow(flow_id="flow-404", src=FlowEndpoint("unknown-01", "https"),
             dst=FlowEndpoint("dc-pi-09", "https")),
        now=1_700_000_000)
    assert d.decision is FlowDecisionKind.ALLOW
    assert d.rule_id is None and d.matched is False
    assert "default monitor" in d.reason


def test_empty_policy_denies_everything():
    pol = FlowPolicy(policy_id="pol-empty", rules=[])
    d = DecisionEngine(pol).evaluate(flow(), now=1)
    assert d.decision is FlowDecisionKind.BLOCK and d.rule_id is None


# ---------- determinism + contract fields ----------

def test_deterministic_decision():
    eng = DecisionEngine(demo_policy())
    f = flow()
    a = eng.evaluate(f, trace_id="t", now=1_700_000_000)
    b = eng.evaluate(f, trace_id="t", now=1_700_000_000)
    assert a.content_hash() == b.content_hash()
    for field in ("decision", "reason", "rule_id", "policy_id",
                  "policy_version", "ttl_s", "decided_at"):
        assert getattr(a, field) == getattr(b, field)


def test_decision_record_contract_fields():
    d = DecisionEngine(demo_policy()).evaluate(
        flow(), trace_id="trace-xyz", now=1_700_000_000)
    rec = d.as_record()
    assert rec["schema_version"] == 1
    assert rec["enforcement"] == "simulated"   # never claims real enforcement
    assert rec["provenance"] == "DEMO"
    assert rec["trace_id"] == "trace-xyz"
    assert rec["flow"]["src"] == {"node_id": "lab-client-01", "service": "https"}
    assert rec["content_hash"] == d.content_hash()
    assert rec["decided_at"].endswith("Z")


def test_provenance_passthrough_replay():
    d = DecisionEngine(demo_policy()).evaluate(
        flow(provenance=Provenance.REPLAY), now=1)
    assert d.provenance is Provenance.REPLAY
    assert d.as_record()["provenance"] == "REPLAY"


# ---------- malformed flow rejection ----------

@pytest.mark.parametrize("bad_id", ["", "has space", "semi;colon", "x" * 129,
                                    "../../etc", "ünïcode"])
def test_malformed_flow_id_rejected(bad_id):
    with pytest.raises(FlowValidationError):
        flow(flow_id=bad_id)


def test_non_endpoint_src_rejected():
    with pytest.raises(FlowValidationError):
        FlowTuple(flow_id="f1", src="lab-client-01", dst=PROTECTED,
                  provenance=Provenance.DEMO)


def test_bad_service_rejected():
    with pytest.raises(FlowValidationError):
        FlowEndpoint("node-1", "HTTP Service!")


def test_bad_provenance_rejected():
    with pytest.raises(FlowValidationError):
        flow(provenance="SYNTHETIC")


def test_oversized_trace_id_rejected():
    with pytest.raises(FlowValidationError):
        DecisionEngine(demo_policy()).evaluate(flow(), trace_id="x" * 129, now=1)


# ---------- policy/rule validation ----------

def test_redirect_rule_requires_target():
    with pytest.raises(FlowValidationError):
        FlowRule("r1", FlowMatch(dst_service="ssh"),
                 FlowDecisionKind.REDIRECT)


def test_non_redirect_forbids_target():
    with pytest.raises(FlowValidationError):
        FlowRule("r1", FlowMatch(), FlowDecisionKind.ALLOW,
                 redirect_to=DECOY)


def test_duplicate_rule_ids_rejected():
    r = FlowRule("dup", FlowMatch(), FlowDecisionKind.ALLOW)
    with pytest.raises(FlowValidationError):
        FlowPolicy(policy_id="p", rules=[r, r])


def test_bad_default_action_rejected():
    with pytest.raises(FlowValidationError):
        FlowPolicy(policy_id="p", default_action="maybe")


def test_bad_ttl_rejected():
    with pytest.raises(FlowValidationError):
        FlowRule("r", FlowMatch(), FlowDecisionKind.ALLOW, ttl_s=0)
    with pytest.raises(FlowValidationError):
        FlowPolicy(policy_id="p", default_ttl_s=99999)


def test_bad_action_rejected():
    with pytest.raises(FlowValidationError):
        FlowRule("r", FlowMatch(), "maybe")
