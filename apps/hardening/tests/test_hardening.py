import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hardening import (  # noqa: E402
    FixtureAdapter, FixSpec, HState, HardeningGate,
)

CAND = {"candidate_id": "cand-1", "node_ref": "vpi-compute-01",
        "title": "Posture: missing_patch on vpi-compute-01",
        "severity": "high", "confidence": "confirmed"}
FIX = FixSpec("ssh_password_auth", False)


def gate():
    return HardeningGate(FixtureAdapter(
        {"vpi-compute-01": {"ssh_password_auth": True}}))


def propose_ok(g=None):
    g = g or gate()
    p, why = g.propose(CAND, FIX, "agent-1", "agent",
                       "disable password auth per posture finding")
    assert why == "ok", why
    return g, p


def approve(g, p, approver="cmd-1", role="commander"):
    return g.approve(p.proposal_id, approver, role, p.fingerprint)


def test_full_lifecycle_verified():
    g, p = propose_ok()
    ok, why = approve(g, p)
    assert ok, why
    ok, why = g.execute(p.proposal_id)
    assert ok and why == "verified"
    assert p.state == HState.VERIFIED
    # independent read confirms value actually applied
    assert g.adapter.read_config("vpi-compute-01")["ssh_password_auth"] is False


def test_fix_allowlist_enforced():
    g = gate()
    p, why = g.propose(CAND, FixSpec("rm_rf_root", True), "a", "agent")
    assert p is None and why == "fix_not_allowlisted"
    p, why = g.propose(CAND, FixSpec("ssh_password_auth", True), "a", "agent")
    assert p is None and why == "fix_not_allowlisted"  # wrong direction


def test_self_approval_denied():
    g, p = propose_ok()
    ok, why = approve(g, p, approver="agent-1", role="commander")
    assert not ok and "self_approval" in why


def test_non_approver_role_denied():
    g, p = propose_ok()
    ok, why = approve(g, p, approver="responder-1", role="responder")
    assert not ok and "role" in why


def test_fingerprint_replay_denied():
    g, p = propose_ok()
    approve(g, p)
    # second proposal same candidate+fix -> duplicate id, can't reuse fp
    p2, why = g.propose(CAND, FIX, "agent-2", "agent")
    assert why == "duplicate"
    # tampered fingerprint denied
    g2, p3 = propose_ok()
    ok, why = g2.approve(p3.proposal_id, "cmd", "commander", "deadbeef")
    assert not ok and "fingerprint" in why


def test_expiry_denied():
    g, p = propose_ok()
    past = time.time() + 10000
    # force expiry by backdating created_at
    p.created_at = time.time() - 2000
    ok, why = g.approve(p.proposal_id, "cmd-1", "commander",
                        p.fingerprint, now=time.time())
    assert not ok and why == "expired"
    assert p.state == HState.EXPIRED


def test_execute_requires_approved():
    g, p = propose_ok()
    ok, why = g.execute(p.proposal_id)
    assert not ok and "bad_state" in why


def test_verify_failure_not_silent():
    """Adapter apply ack but read shows wrong value -> FAILED."""
    class LyingAdapter(FixtureAdapter):
        def apply_fix(self, node, fix):
            return {"ack": True}   # claims success, doesn't write
    g = HardeningGate(LyingAdapter({"vpi-compute-01": {}}))
    p, _ = g.propose(CAND, FIX, "a", "agent")
    approve(g, p)
    ok, why = g.execute(p.proposal_id)
    assert not ok and why == "verify_failed"
    assert p.state == HState.FAILED


def test_duplicate_proposal_returns_existing():
    g, p1 = propose_ok()
    p2, why = g.propose(CAND, FIX, "agent-9", "agent")
    assert why == "duplicate" and p2.proposal_id == p1.proposal_id
