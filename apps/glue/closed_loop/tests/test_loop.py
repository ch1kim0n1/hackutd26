"""GLUE-05: approval->containment->verification closed loop."""
import pytest

from closed_loop import (
    ApprovalService,
    ClosedLoop,
    Denied,
    IndependentVerifier,
    LabExecutor,
    Outbox,
    Proposal,
)


def rig(probe=lambda t: True):
    ap = ApprovalService()
    loop = ClosedLoop(ap, Outbox(), LabExecutor({"lab-01", "lab-02"}),
                      IndependentVerifier(probe))
    return ap, loop


def prop(**kw):
    d = dict(proposal_id="prop-1", action_type="isolate_endpoint",
             target_id="lab-01", incident_id="inc-1")
    d.update(kw)
    return Proposal(**d)


def test_full_loop_verified(ap_loop=None):
    ap, loop = rig()
    p = prop()
    loop.submit(p, "cmd-1", "commander")
    res = loop.process_next()
    assert res["state"] == "VERIFIED"
    stages = [t["stage"] for t in loop.timeline]
    assert stages == ["approved_queued", "verified"]
    # team update posted
    assert loop.chat_posts[-1]["kind"] == "system"
    assert "VERIFIED" in loop.chat_posts[-1]["body"]


def test_wrong_role_denied():
    ap, loop = rig()
    with pytest.raises(Denied, match="role"):
        loop.submit(prop(), "resp-1", "responder")
    with pytest.raises(Denied, match="role"):
        loop.submit(prop(), "agent-1", "agent")


def test_expired_approval_denied():
    now = [1000.0]
    ap = ApprovalService(clock=lambda: now[0])
    loop = ClosedLoop(ap, Outbox(), LabExecutor({"lab-01"}),
                      IndependentVerifier(lambda t: True),
                      clock=lambda: now[0])
    p = prop()
    aid = ap.approve("cmd-1", "commander", p)
    now[0] += 400                                # past 300s TTL
    fp = ap.fingerprint_for(p)
    with pytest.raises(Denied, match="expired"):
        ap.consume(aid, fp)


def test_replay_denied():
    ap, loop = rig()
    p = prop()
    aid = ap.approve("cmd-1", "commander", p)
    fp = ap.fingerprint_for(p)
    ap.consume(aid, fp)
    with pytest.raises(Denied, match="replay|consumed"):
        ap.consume(aid, fp)


def test_fingerprint_mismatch_denied():
    ap, loop = rig()
    p = prop()
    aid = ap.approve("cmd-1", "commander", p)
    tampered = prop(target_id="lab-02")
    with pytest.raises(Denied, match="does not match"):
        ap.consume(aid, ap.fingerprint_for(tampered))


def test_self_approval_denied():
    ap, loop = rig()
    p = prop(proposed_by="cmd-1")
    with pytest.raises(Denied, match="separation"):
        ap.approve("cmd-1", "commander", p)


def test_verify_failure_displayed():
    # probe says target still reachable -> FAILED, never VERIFIED
    ap, loop = rig(probe=lambda t: False)
    loop.submit(prop(), "cmd-1", "commander")
    res = loop.process_next()
    assert res["state"] == "FAILED" and res["stage"] == "verify"
    assert "still reachable" in res["reason"]
    assert "FAILED" in loop.chat_posts[-1]["body"]


def test_non_lab_target_denied():
    ap, loop = rig()
    loop.submit(prop(target_id="prod-db"), "cmd-1", "commander")
    res = loop.process_next()
    assert res["state"] == "FAILED" and res["stage"] == "exec"


def test_outbox_idempotent():
    ap, loop = rig()
    p = prop()
    aid = ap.approve("cmd-1", "commander", p)
    r1 = loop.outbox.enqueue(aid, p)
    r2 = loop.outbox.enqueue(aid, p)
    assert r1 is r2 and len(loop.outbox.records) == 1
