import json

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
    Provenance,
    DecisionLog,
)


def make_decision(flow_id="flow-001", outcome=None):
    pol = FlowPolicy(policy_id="pol-log", rules=[
        FlowRule("r-allow", FlowMatch(dst_service="http"),
                 FlowDecisionKind.ALLOW),
        FlowRule("r-block", FlowMatch(dst_service="ssh"),
                 FlowDecisionKind.BLOCK),
    ])
    dst = FlowEndpoint("dc-pi-01", outcome or "http")
    f = FlowTuple(flow_id=flow_id,
                  src=FlowEndpoint("lab-client-01", "https"), dst=dst,
                  provenance=Provenance.DEMO)
    return DecisionEngine(pol).evaluate(f, trace_id="t-log", now=1_700_000_000)


def test_append_and_verify():
    log = DecisionLog()
    d1 = make_decision("flow-a")
    d2 = make_decision("flow-b", outcome="ssh")
    r1 = log.append(d1)
    r2 = log.append(d2)
    assert r1.seq == 0 and r2.seq == 1
    assert r2.prev_hash == r1.hash
    assert log.verify() == (True, "chain intact")


def test_record_carries_contract_and_provenance():
    log = DecisionLog()
    rec = log.append(make_decision())
    d = rec.decision
    assert d["schema_version"] == 1
    assert d["enforcement"] == "simulated"
    assert d["provenance"] == "DEMO"
    assert d["policy_id"] == "pol-log"
    assert d["trace_id"] == "t-log"
    assert rec.trace_id == "t-log"


def test_tamper_detection():
    log = DecisionLog()
    log.append(make_decision())
    log.append(make_decision("flow-b", outcome="ssh"))
    # tamper with a stored record's content
    log.records_list[0].decision["decision"] = "block"
    ok, msg = log.verify()
    assert ok is False and "hash mismatch" in msg


def test_seq_gap_detection():
    log = DecisionLog()
    log.append(make_decision())
    log.records_list[0].seq = 7
    ok, msg = log.verify()
    assert ok is False


def test_persistence_reload(tmp_path):
    p = tmp_path / "decisions.jsonl"
    log = DecisionLog(p)
    log.append(make_decision("flow-a"))
    log.append(make_decision("flow-b", outcome="ssh"))

    log2 = DecisionLog(p)
    assert len(log2.records_list) == 2
    assert log2.verify() == (True, "chain intact")
    assert log2.records(flow_id="flow-b")[0].outcome == "block"


def test_filters():
    log = DecisionLog()
    log.append(make_decision("flow-a"))
    log.append(make_decision("flow-b", outcome="ssh"))
    assert len(log.records(flow_id="flow-a")) == 1
    assert len(log.records(outcome="block")) == 1
    assert len(log.records(policy_id="pol-log")) == 2
    assert len(log.records(policy_id="other")) == 0


def test_append_rejects_non_decision():
    with pytest.raises(TypeError):
        DecisionLog().append({"not": "a decision"})


def test_default_monitor_recorded_as_unmatched():
    pol = FlowPolicy(policy_id="pol-mon",
                     default_action=DefaultAction.MONITOR, rules=[])
    f = FlowTuple(flow_id="flow-x",
                  src=FlowEndpoint("n-1", "https"),
                  dst=FlowEndpoint("n-2", "https"),
                  provenance=Provenance.DEMO)
    d = DecisionEngine(pol).evaluate(f, now=1)
    rec = DecisionLog().append(d)
    assert rec.decision["decision"] == "allow"
    assert rec.decision["rule_id"] is None
    assert "default monitor" in rec.decision["reason"]
