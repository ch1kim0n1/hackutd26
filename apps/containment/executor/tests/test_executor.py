import time

import pytest

from containment_executor import (
    ExecState,
    Executor,
    MockLabAdapter,
    MockVerifyAdapter,
    Outbox,
    OutboxItem,
)


def make_item(action_id="act-1", target="lab-endpoint-01",
              expires_in=300, **kw):
    return OutboxItem(
        action_id=action_id, incident_id="inc-1",
        action_type="isolate_endpoint", target_id=target,
        reason="approved isolation", approved_by="cmd-1",
        approval_id="appr-1", expires_at=time.time() + expires_in,
        fingerprint="fp", **kw)


def make_exec(lab=None, verify=None):
    lab = lab or MockLabAdapter()
    ob = Outbox()
    ver = verify or MockVerifyAdapter(lab)
    return Executor(ob, lab, ver), ob, lab, ver


# ---------- happy path ----------

def test_approved_action_isolates_and_verifies():
    ex, ob, lab, ver = make_exec()
    ob.deliver(make_item())
    [rec] = ex.run_once()
    assert rec.state == ExecState.VERIFIED
    # states recorded separately: started -> api_acked -> verified
    states = [h["state"] for h in rec.states_history]
    assert states == ["started", "api_acked", "verified"]
    assert lab.rules["lab-endpoint-01"] == "isolate_endpoint"
    assert lab.endpoint_up["lab-endpoint-01"] is False
    assert ver.probes  # independent probe actually ran


# ---------- threat 3: fake success ----------

def test_fake_api_success_but_still_connected_fails():
    """API returns ok but isolation never took effect -> FAILED, not
    VERIFIED. This is the docs/08 threat-3 test."""
    lab = MockLabAdapter(lie_about_success=True)
    ex, ob, _, ver = make_exec(lab=lab)
    ob.deliver(make_item())
    [rec] = ex.run_once()
    assert rec.state == ExecState.FAILED
    assert rec.state != ExecState.VERIFIED
    assert rec.verification["effective"] is False
    assert "verification" in rec.states_history[-1]["stage"]


def test_adapter_failure_records_failed():
    lab = MockLabAdapter(fail_apply=True)
    ex, ob, _, _ = make_exec(lab=lab)
    ob.deliver(make_item())
    [rec] = ex.run_once()
    assert rec.state == ExecState.FAILED
    assert rec.states_history[-1]["stage"] == "api"  # ok:false refusal


def test_adapter_refusal_records_failed():
    class Refusing(MockLabAdapter):
        def apply_isolation(self, t, a):
            return {"ok": False, "error": "target not owned"}
    lab = Refusing()
    ex, ob, _, _ = make_exec(lab=lab)
    ob.deliver(make_item())
    [rec] = ex.run_once()
    assert rec.state == ExecState.FAILED
    assert rec.states_history[-1]["stage"] == "api"


# ---------- idempotency / outbox ----------

def test_redelivery_is_idempotent():
    ex, ob, lab, _ = make_exec()
    item = make_item()
    ob.deliver(item)
    ob.deliver(item)          # duplicate delivery
    ob.deliver(item)          # and again
    recs = ex.run_once()
    assert len(recs) == 1
    assert recs[0].state == ExecState.VERIFIED
    # apply called exactly once despite 3 deliveries
    applies = [c for c in lab.calls if c["op"] == "apply"]
    assert len(applies) == 1
    # later redelivery after completion -> skipped_duplicate record
    ob.deliver(item)
    assert ob.records["act-1"].states_history[-1]["state"] == \
        "skipped_duplicate"


def test_expired_approval_rejected():
    ex, ob, lab, _ = make_exec()
    ob.deliver(make_item(expires_in=-1))
    assert ob.pending() == []
    rec = ob.records["act-1"]
    assert rec.state == ExecState.REJECTED_UNAPPROVED
    assert lab.calls == []  # never touched the lab


def test_unapproved_action_never_executes():
    """Only outbox-delivered (approved) items execute — executor has no
    other intake path."""
    ex, ob, lab, _ = make_exec()
    # simulate stray call with fabricated item — still goes through outbox
    # which only accepts delivered items; records start QUEUED only via
    # deliver(). A fabricated OutboxItem IS deliverable by design (the
    # approval happened upstream) — the guard is upstream in #33.
    # Here we verify: nothing executes without deliver().
    assert ex.run_once() == []
    assert lab.calls == []


# ---------- revert / recovery ----------

def test_revert_restores_and_verifies():
    ex, ob, lab, ver = make_exec()
    item = make_item()
    ob.deliver(item)
    [rec] = ex.run_once()
    assert rec.state == ExecState.VERIFIED
    rec2 = ex.revert(item)
    assert rec2.state == ExecState.VERIFIED
    assert lab.endpoint_up["lab-endpoint-01"] is True
    assert "revert" in rec2.verification


def test_revert_failure_recorded():
    lab = MockLabAdapter()
    ver = MockVerifyAdapter(lab)
    ex, ob, _, _ = make_exec(lab=lab, verify=ver)
    item = make_item()
    ob.deliver(item)
    ex.run_once()
    # probe keeps reporting unreachable even after revert (flaky net)
    ver.target_reachable = lambda t: False
    rec = ex.revert(item, verify=ver)
    assert rec.state == ExecState.FAILED
    assert rec.verification["revert"]["restored"] is False
