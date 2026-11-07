import json

import pytest

from response_audit import (
    AuditLog,
    RecoveryDenied,
    RecoveryService,
    RecoveryState,
)


# ---------- audit log ----------

def test_audit_distinguishes_lifecycle_operations():
    log = AuditLog()
    log.append(actor="agent-1", actor_role="agent", operation="propose",
               entity_type="action", entity_id="act-1", incident_id="inc-1",
               reason="rogue AP")
    log.append(actor="cmd-1", actor_role="commander", operation="approve",
               entity_type="action", entity_id="act-1", incident_id="inc-1",
               reason="evidence sufficient")
    log.append(actor="exec-1", actor_role="executor", operation="execute",
               entity_type="action", entity_id="act-1", incident_id="inc-1",
               verification={"effective": True})
    log.append(actor="exec-1", actor_role="executor", operation="verify",
               entity_type="action", entity_id="act-1", incident_id="inc-1",
               verification={"reachable": False})
    ops = log.operations_for("act-1")
    assert ops == ["propose", "approve", "execute", "verify"]
    # timeline scoped by incident
    assert len(log.timeline(incident_id="inc-1")) == 4
    assert log.timeline(incident_id="inc-2") == []


def test_audit_hash_chain_detects_tamper():
    log = AuditLog()
    for i in range(3):
        log.append(actor=f"a{i}", actor_role="r", operation="op",
                   entity_type="e", entity_id="x", incident_id="inc",
                   reason=f"r{i}")
    ok, msg = log.verify()
    assert ok, msg
    # tamper with a historical entry
    log.entries[1].reason = "FORGED"
    ok, msg = log.verify()
    assert not ok and "hash mismatch" in msg


def test_audit_persists_and_reloads(tmp_path):
    p = tmp_path / "audit.jsonl"
    log = AuditLog(p)
    log.append(actor="a", actor_role="r", operation="propose",
               entity_type="action", entity_id="act-9", incident_id="inc-1",
               reason="test")
    log2 = AuditLog(p)
    assert len(log2.entries) == 1
    assert log2.entries[0].entity_id == "act-9"
    assert log2.verify()[0]


def test_audit_actor_and_entity_filters():
    log = AuditLog()
    log.append(actor="cmd-1", actor_role="commander", operation="approve",
               entity_type="action", entity_id="act-1", incident_id="inc-1")
    log.append(actor="resp-1", actor_role="responder", operation="note",
               entity_type="incident", entity_id="inc-1", incident_id="inc-1")
    assert len(log.timeline(actor="cmd-1")) == 1
    assert len(log.timeline(entity_id="inc-1")) == 1


# ---------- recovery ----------

def _setup():
    log = AuditLog()
    svc = RecoveryService(log)
    return log, svc


def test_recovery_requires_approval():
    _, svc = _setup()
    r = svc.propose(action_id="act-1", incident_id="inc-1",
                    target_id="lab-endpoint-01",
                    reason="incident resolved, restore service",
                    requester_id="resp-1")
    with pytest.raises(RecoveryDenied):
        svc.execute(r.recovery_id, revert_fn=lambda t, a: {},
                    verify_fn=lambda t: True)


def test_recovery_denies_wrong_role_and_self_approval():
    log, svc = _setup()
    r = svc.propose(action_id="act-1", incident_id="inc-1",
                    target_id="t", reason="restore after fix",
                    requester_id="cmd-1")
    with pytest.raises(RecoveryDenied):
        svc.approve(r.recovery_id, approver_id="resp-1",
                    approver_role="responder")
    # self-approval even by commander denied
    with pytest.raises(RecoveryDenied):
        svc.approve(r.recovery_id, approver_id="cmd-1",
                    approver_role="commander")
    # proper different commander approves
    svc.approve(r.recovery_id, approver_id="cmd-2",
                approver_role="commander", reason="ok")
    assert r.state == RecoveryState.APPROVED


def test_recovery_executes_revert_and_verifies():
    log, svc = _setup()
    calls = []

    def revert_fn(target, action):
        calls.append(("revert", target, action))
        return {"ok": True}

    def verify_fn(target):
        calls.append(("verify", target))
        return True

    r = svc.propose(action_id="act-1", incident_id="inc-1",
                    target_id="lab-endpoint-01",
                    reason="restore lab endpoint connectivity",
                    requester_id="resp-1")
    svc.approve(r.recovery_id, approver_id="cmd-2",
                approver_role="commander")
    svc.execute(r.recovery_id, revert_fn=revert_fn, verify_fn=verify_fn)
    assert r.state == RecoveryState.RECOVERED
    ops = log.operations_for("act-1")
    assert "recover_propose" in ops and "recover_approve" in ops
    assert "recover_revert" in ops and "recover_verify" in ops
    assert "recover_result" in ops


def test_recovery_failed_when_verify_fails():
    log, svc = _setup()
    r = svc.propose(action_id="act-1", incident_id="inc-1",
                    target_id="t", reason="restore service now please",
                    requester_id="resp-1")
    svc.approve(r.recovery_id, approver_id="admin-1", approver_role="admin")
    svc.execute(r.recovery_id, revert_fn=lambda t, a: {"ok": True},
                verify_fn=lambda t: False)
    assert r.state == RecoveryState.RECOVERY_FAILED
    # audit shows verification failed, not silent success
    verify_entries = [e for e in log.timeline(entity_id="act-1")
                      if e.operation == "recover_verify"]
    assert verify_entries[0].verification["restored"] is False


def test_recovery_audit_full_chain():
    log, svc = _setup()
    r = svc.propose(action_id="act-1", incident_id="inc-1",
                    target_id="t", reason="restore endpoint service ok",
                    requester_id="resp-1")
    svc.approve(r.recovery_id, approver_id="cmd-9",
                approver_role="commander")
    svc.execute(r.recovery_id, revert_fn=lambda t, a: {},
                verify_fn=lambda t: True)
    assert log.verify()[0]
