"""#113 — policy-approved actions + outcome verification, per capability.

Module-side chain (proposeAction -> recordApproval -> claimOutbox ->
recordExecutorOutcome -> verifyContainment) is covered by
spacetimedb/tests/smoke.ts. This suite proves the package-level half:
each capability produces an executor-ready outbox doc + independently
verified outcome, and every denial path holds.
"""
import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for rel in ("quarantine/src", "containment/executor/src",
            "datacenter/services", "hardening/src", "deception/src",
            "defense/gateway/src"):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from quarantine import HealthProbeVerify, NodeLabAdapter  # noqa: E402
from hardening.engine import FixtureAdapter, FixSpec, HardeningGate  # noqa: E402
from deception import DeceptionRouter, deception_policy, flow  # noqa: E402
from defense_gateway.engine import DecisionEngine  # noqa: E402
import vpi_service  # noqa: E402


def _vpi_node():
    srv = vpi_service.make_server("vpi-compute-01", "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


# ---------------------------------------------------------------------------
# capability 1: quarantine — approved action -> executor -> VERIFIED
# ---------------------------------------------------------------------------

def test_quarantine_capability_verified():
    from containment_executor.service import ExecutorService
    srv, url = _vpi_node()
    try:
        svc = ExecutorService(
            lab=NodeLabAdapter({"vpi-compute-01": url}),
            verify=HealthProbeVerify({"vpi-compute-01": url}))
        # doc shape == what module claimOutbox delivers to executor
        doc = {"schema_version": 1, "action_id": "a-q1",
               "incident_id": "inc-1", "type": "quarantine_vlan",
               "target_id": "vpi-compute-01", "fingerprint": "fp1",
               "approval_id": "appr-1"}
        status, rec = svc.execute(doc)
        assert status == 200 and rec["state"] == "verified"
        # audit fields the module needs for recordExecutorOutcome
        assert rec["action_id"] == "a-q1" and rec["incident_id"] == "inc-1"
        assert rec["verification"]["method"] == "independent_probe"
    finally:
        srv.shutdown()


def test_quarantine_verify_lie_is_failed():
    """Adapter acks but node never isolates -> FAILED, never VERIFIED."""
    from containment_executor.service import ExecutorService
    from containment_executor.adapters import LabAdapter

    class LyingLab:
        def apply_isolation(self, t, a):
            return {"ok": True}  # claims success, does nothing
        def remove_isolation(self, t, a):
            return {"ok": True}

    class NeverEffective:
        def target_reachable(self, t):
            return True
        def isolation_effective(self, t, a):
            return False

    svc = ExecutorService(lab=LyingLab(), verify=NeverEffective())
    doc = {"schema_version": 1, "action_id": "a-q2",
           "incident_id": "inc-2", "type": "isolate_endpoint",
           "target_id": "n1", "fingerprint": "fp2",
           "approval_id": "appr-2"}
    status, rec = svc.execute(doc)
    assert status == 502 and rec["state"] == "failed"
    assert rec["verification"]["effective"] is False


def test_quarantine_unapproved_action_type_denied():
    lab = NodeLabAdapter({})
    with pytest.raises(Exception):
        lab.apply_isolation("n1", "shell_exec")


# ---------------------------------------------------------------------------
# capability 2: preventive hardening — propose/approve/execute/verify
# ---------------------------------------------------------------------------

def test_hardening_capability_verified_and_audited():
    gate = HardeningGate(FixtureAdapter(), secret=b"pa")
    prop, st = gate.propose(
        {"candidate_id": "cand-1", "node_ref": "vpi-compute-01",
         "title": "ssh password auth enabled"},
        FixSpec(key="ssh_password_auth", value=False),
        proposer_id="agent-nemotron", proposer_role="agent")
    assert st == "ok"
    # proposer cannot approve (SoD)
    ok, msg = gate.approve(prop.proposal_id, "agent-nemotron",
                           "agent", prop.fingerprint)
    assert not ok
    ok, msg = gate.approve(prop.proposal_id, "cmd-1", "commander",
                           prop.fingerprint)
    assert ok
    ok, msg = gate.execute(prop.proposal_id)
    assert ok and prop.state.value == "verified"
    # audit: approvals recorded with actor + fingerprint
    assert prop.approvals[0]["by"] == "cmd-1"
    assert prop.approvals[0]["fp"] == prop.fingerprint


def test_hardening_expired_and_replay_denied():
    import time
    gate = HardeningGate(FixtureAdapter(), secret=b"pa2")
    p1, _ = gate.propose({"candidate_id": "c1", "node_ref": "n1"},
                         FixSpec(key="mqtt_tls", value=True),
                         proposer_id="a", proposer_role="agent")
    p1.created_at = time.time() - 99999
    ok, msg = gate.approve(p1.proposal_id, "cmd", "commander",
                           p1.fingerprint)
    assert not ok and msg == "expired"
    # fingerprint replay across proposals
    p2, _ = gate.propose({"candidate_id": "c2", "node_ref": "n1"},
                         FixSpec(key="auto_updates", value=True),
                         proposer_id="b", proposer_role="agent")
    p3, _ = gate.propose({"candidate_id": "c3", "node_ref": "n2"},
                         FixSpec(key="auto_updates", value=True),
                         proposer_id="c", proposer_role="agent")
    gate.approve(p2.proposal_id, "cmd1", "commander", p2.fingerprint)
    ok, msg = gate.approve(p3.proposal_id, "cmd2", "commander",
                           p2.fingerprint)  # replay p2's fp
    assert not ok and "fingerprint" in msg


# ---------------------------------------------------------------------------
# capability 3: interception/redirect — policy decision + decoy evidence
# ---------------------------------------------------------------------------

def test_interception_capability_evidence_chain():
    import http.server

    class Decoy(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            out = json.dumps({"device_id": "decoy-01",
                              "synthetic": True,
                              "trace_id": "decoy-x"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    class Backend(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            out = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    decoy = http.server.HTTPServer(("127.0.0.1", 0), Decoy)
    back = http.server.HTTPServer(("127.0.0.1", 0), Backend)
    for s in (decoy, back):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        ev = []
        router = DeceptionRouter(
            engine=DecisionEngine(deception_policy(
                redirect_src_nodes=("attacker-01",))),
            backends={"vpi-01": f"http://127.0.0.1:{back.server_address[1]}"},
            decoy_url=f"http://127.0.0.1:{decoy.server_address[1]}",
            evidence_sink=ev.append)
        res = router.route(flow("pa-int-1", "attacker-01", "vpi-01"), "/x")
        assert res.action == "redirect" and res.status == 200
        e = res.evidence
        # audit chain fields required downstream
        for k in ("trace_id", "decision_id", "flow_id", "rule_id",
                  "action", "outcome", "provenance", "enforcement"):
            assert k in e, k
        assert e["decoy"]["synthetic"] is True
    finally:
        decoy.shutdown(); back.shutdown()


# ---------------------------------------------------------------------------
# agent/actuator boundary — structural proof
# ---------------------------------------------------------------------------

def test_agent_packages_have_no_actuator_surface():
    """Agent-side packages must not import executor/adapter clients.

    Interface-level proof: nemotron_client, investigator, agent_safety
    contain no reference to containment_executor, NodeLabAdapter,
    HealthProbeVerify, or executor HTTP endpoints. Agents propose;
    only the executor principal actuates.
    """
    agent_dirs = [ROOT / "agent"]
    forbidden = ("containment_executor", "NodeLabAdapter",
                 "HealthProbeVerify", "EXECUTOR_WEBHOOK",
                 "apply_isolation", "admin/isolate")
    hits = []
    for d in agent_dirs:
        for f in d.rglob("*.py"):
            if "__pycache__" in str(f):
                continue
            text = f.read_text()
            for tok in forbidden:
                if tok in text:
                    hits.append(f"{f}:{tok}")
    assert not hits, f"agent packages reference actuator surface: {hits}"


def test_executor_requires_token_auth():
    """Executor service rejects unauthenticated execute calls."""
    from containment_executor.service import ExecutorService, make_handler
    import http.server
    svc = ExecutorService()
    srv = http.server.HTTPServer(("127.0.0.1", 0),
                                 make_handler(svc, "secret-token"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/execute"
        req = urllib.request.Request(
            url, data=b"{}", headers={"Content-Type": "application/json"},
            method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            pytest.fail("unauthenticated call should be rejected")
        except urllib.error.HTTPError as e:
            assert e.code in (401, 403)
    finally:
        srv.shutdown()
