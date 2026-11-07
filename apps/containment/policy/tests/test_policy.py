import pytest

from containment_policy import (
    ActionState,
    ContainmentPolicy,
    Role,
)

SECRET = b"test-fingerprint-secret"
TARGETS = {"lab-endpoint-01", "lab-ap-01", "switch-port-3"}


def make_policy(**kw):
    return ContainmentPolicy(allowed_targets=TARGETS,
                             fingerprint_secret=SECRET, **kw)


def propose(pol, **kw):
    args = dict(incident_id="inc-1", action_type="isolate_endpoint",
                target_id="lab-endpoint-01", reason="confirmed rogue AP "
                "on known SSID with cabinet event", proposer_id="agent-1",
                proposer_role=Role.AGENT)
    args.update(kw)
    return pol.propose(**args)


def approve(pol, prop, **kw):
    args = dict(proposal_id=prop.proposal_id, approver_id="cmd-1",
                approver_role=Role.COMMANDER, decision="approve",
                fingerprint=prop.fingerprint)
    args.update(kw)
    return pol.decide(**args)


# ---------- propose ----------

def test_propose_happy_path():
    pol = make_policy()
    r = propose(pol)
    assert r.ok and r.proposal.state == ActionState.PROPOSED
    assert r.proposal.fingerprint


def test_propose_denies_bad_role():
    pol = make_policy()
    r = propose(pol, proposer_role=Role.OBSERVER)
    assert not r.ok and "may not propose" in r.reason
    r = propose(pol, proposer_id="dev-1", proposer_role=Role.DEVICE)
    assert not r.ok


def test_propose_denies_wrong_target():
    pol = make_policy()
    r = propose(pol, target_id="production-db-01")
    assert not r.ok and "allowlist" in r.reason
    r = propose(pol, target_id="lab-endpoint-01.evil.com")
    assert not r.ok


def test_propose_denies_bad_enums_and_short_reason():
    pol = make_policy()
    assert not propose(pol, action_type="run_shell").ok
    assert not propose(pol, action_type="").ok
    assert not propose(pol, reason="short").ok
    assert not propose(pol, ttl_s=0).ok
    assert not propose(pol, ttl_s=99999).ok


def test_propose_incident_scope():
    pol = make_policy(allowed_incidents={"inc-1"})
    assert propose(pol, incident_id="inc-1").ok
    assert not propose(pol, incident_id="inc-OTHER").ok


# ---------- approve ----------

def test_approve_happy_path():
    pol = make_policy()
    p = propose(pol).proposal
    r = approve(pol, p)
    assert r.ok and p.state == ActionState.APPROVED
    assert r.approval.approver_id == "cmd-1"
    assert pol.approved_actions() == [p]


def test_approve_denies_self_approval():
    pol = make_policy()
    p = propose(pol, proposer_id="cmd-1", proposer_role=Role.COMMANDER).proposal
    r = approve(pol, p, approver_id="cmd-1")
    assert not r.ok and "self-approval" in r.reason


def test_approve_denies_wrong_role():
    pol = make_policy()
    p = propose(pol).proposal
    assert not approve(pol, p, approver_role=Role.RESPONDER).ok
    assert not approve(pol, p, approver_role=Role.AGENT).ok
    # observer can't even deny
    assert not approve(pol, p, approver_role=Role.OBSERVER,
                       decision="deny").ok


def test_approve_denies_fingerprint_mismatch():
    pol = make_policy()
    p = propose(pol).proposal
    r = approve(pol, p, fingerprint="0" * 64)
    assert not r.ok and "fingerprint mismatch" in r.reason
    # tampered proposal fields -> fingerprint no longer matches
    p.target_id = "switch-port-3"
    r = approve(pol, p)  # uses p.fingerprint which was computed pre-tamper
    assert not r.ok


def test_approve_denies_expired_proposal():
    now = [1000.0]
    pol = make_policy(clock=lambda: now[0])
    p = propose(pol, ttl_s=10).proposal
    now[0] += 11
    r = approve(pol, p)
    assert not r.ok and "expired" in r.reason
    assert p.state == ActionState.EXPIRED


def test_approve_replay_duplicate_fingerprint():
    pol = make_policy()
    p = propose(pol).proposal
    assert approve(pol, p).ok
    # second decide on same proposal -> state no longer PROPOSED
    r2 = approve(pol, p, approver_id="cmd-2")
    assert not r2.ok
    # a different proposal can still be decided (fingerprints unique)
    p2 = propose(pol, target_id="lab-ap-01").proposal
    assert approve(pol, p2, approver_id="cmd-2").ok


def test_decide_deny_path():
    pol = make_policy()
    p = propose(pol).proposal
    r = approve(pol, p, decision="deny", reason="insufficient evidence")
    assert r.ok and p.state == ActionState.DENIED
    assert pol.approved_actions() == []


def test_state_transitions_guarded():
    pol = make_policy()
    p = propose(pol).proposal
    approve(pol, p)
    from containment_policy import ActionState
    assert pol.mark_state(p.proposal_id, ActionState.EXECUTING,
                          allowed_from={ActionState.APPROVED})
    # can't jump backwards arbitrarily
    assert not pol.mark_state(p.proposal_id, ActionState.PROPOSED,
                              allowed_from={ActionState.PROPOSED})
    assert not pol.mark_state("nonexistent", ActionState.FAILED)


def test_approved_actions_excludes_expired():
    now = [0.0]
    pol = make_policy(clock=lambda: now[0])
    p = propose(pol, ttl_s=10).proposal
    approve(pol, p)
    now[0] = 5.0
    assert pol.approved_actions() == [p]
    now[0] = 20.0
    assert pol.approved_actions() == []
