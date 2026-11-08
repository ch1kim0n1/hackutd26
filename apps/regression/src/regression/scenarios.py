"""#110 regression scenarios: prevention, interception, mitigation.

Each scenario runs the real merged packages end-to-end and returns an
evidence chain (list of dicts) so callers/tests can assert audit
continuity. All lab/synthetic — provenance labels preserved.
"""
from __future__ import annotations

import http.server
import json
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for rel in ("posture/src", "risk_priority/src", "prevention/src",
            "hardening/src", "defense/gateway/src", "deception/src",
            "quarantine/src", "containment/executor/src",
            "datacenter/services"):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from deception import DeceptionRouter, deception_policy, flow  # noqa: E402
from defense_gateway.engine import DecisionEngine  # noqa: E402
from hardening.engine import FixtureAdapter, FixSpec, HardeningGate  # noqa: E402
from posture.engine import PostureEngine, seed_weak_fixture  # noqa: E402
from prevention.workflow import PreventionPolicy, build_candidates  # noqa: E402
from risk_priority.engine import prioritize  # noqa: E402
from quarantine import HealthProbeVerify, NodeLabAdapter  # noqa: E402


# ---------------------------------------------------------------------------
# scenario 1: prevention — posture finding -> risk -> candidate -> hardening
# ---------------------------------------------------------------------------

def prevention_scenario() -> dict:
    findings = PostureEngine(seed_weak_fixture()).assess()
    ranked = prioritize(findings)
    cands = build_candidates(ranked, PreventionPolicy(), tick=1)
    filed = [c for c in cands if c["status"] == "auto_filed"]
    if not filed:
        return {"ok": False, "stage": "no_auto_filed_candidate",
                "findings": len(findings)}

    gate = HardeningGate(FixtureAdapter(), secret=b"regression")
    # pick a fixable finding: ssh_password_auth drift -> disable it
    fix = FixSpec(key="ssh_password_auth", value=False)
    prop, status = gate.propose(
        {"candidate_id": filed[0]["candidate_id"],
         "node_ref": filed[0]["node_ref"],
         "title": filed[0]["title"]},
        fix, proposer_id="agent-nemotron", proposer_role="agent",
        reason="posture drift remediation")
    evidence = [{"stage": "posture", "findings": len(findings),
                 "top_rank": ranked[0]["rank"] if ranked else None},
                {"stage": "candidate", "id": filed[0]["candidate_id"],
                 "status": filed[0]["status"]},
                {"stage": "propose", "status": status,
                 "proposal_id": prop.proposal_id if prop else None}]
    if prop is None:
        return {"ok": False, "stage": "propose_failed", "evidence": evidence}

    ok, msg = gate.approve(prop.proposal_id, "cmd-1", "commander",
                           prop.fingerprint)
    evidence.append({"stage": "approve", "ok": ok, "msg": msg})
    if not ok:
        return {"ok": False, "stage": "approve_failed", "evidence": evidence}

    ok, msg = gate.execute(prop.proposal_id)
    evidence.append({"stage": "execute", "ok": ok, "msg": msg,
                     "state": prop.state.value})
    return {"ok": ok and prop.state.value == "verified",
            "evidence": evidence}


# ---------------------------------------------------------------------------
# scenario 2: interception — malicious flow -> block/redirect -> decoy -> ev
# ---------------------------------------------------------------------------

def _stub_http(handler):
    import http.server
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class _Decoy(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        out = json.dumps({"device_id": "decoy-01", "synthetic": True,
                          "trace_id": "decoy-reg-1"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class _Backend(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        out = b'{"svc":"real"}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def interception_scenario() -> dict:
    decoy = _stub_http(_Decoy)
    backend = _stub_http(_Backend)
    try:
        evidence = []
        router = DeceptionRouter(
            engine=DecisionEngine(deception_policy(
                redirect_src_nodes=("attacker-01",),
                block_src_nodes=("bad-actor",),
                default="monitor")),
            backends={"vpi-01": f"http://127.0.0.1:{backend.server_address[1]}"},
            decoy_url=f"http://127.0.0.1:{decoy.server_address[1]}",
            evidence_sink=evidence.append)

        r1 = router.route(flow("reg-int-1", "attacker-01", "vpi-01",
                               provenance=__import__(
                                   "defense_gateway.models",
                                   fromlist=["Provenance"]).Provenance.DEMO),
                          "/login")
        r2 = router.route(flow("reg-int-2", "bad-actor", "vpi-01"), "/")
        r3 = router.route(flow("reg-int-3", "ops-01", "vpi-01"), "/health")

        ok = (r1.action == "redirect" and r1.status == 200
              and json.loads(r1.body)["device_id"] == "decoy-01"
              and r2.status == 403 and r3.status == 200
              and r1.evidence["decoy"]["decoy_trace"])
        # audit continuity: every route emitted evidence w/ unique ids
        linked = all(e.get("trace_id") and e.get("decision_id")
                     for e in evidence)
        return {"ok": ok and linked and len(evidence) >= 3,
                "evidence": evidence}
    finally:
        decoy.shutdown(); backend.shutdown()


# ---------------------------------------------------------------------------
# scenario 3: mitigation — approved action -> executor -> independent verify
# ---------------------------------------------------------------------------

def mitigation_scenario() -> dict:
    import vpi_service  # noqa: E402  (datacenter/services on sys.path)
    from containment_executor.service import ExecutorService  # noqa: E402

    srv = vpi_service.make_server("vpi-compute-01", "127.0.0.1", 0)
    port = srv.server_addresses[1] if hasattr(srv, "server_addresses") \
        else srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    try:
        svc = ExecutorService(
            lab=NodeLabAdapter({"vpi-compute-01": url}),
            verify=HealthProbeVerify({"vpi-compute-01": url}))
        doc = {
            "schema_version": 1,
            "action_id": "act-reg-1",
            "incident_id": "inc-reg-1",
            "type": "quarantine_vlan",
            "target_id": "vpi-compute-01",
            "fingerprint": "fp-reg-1",
            "approval_id": "appr-reg-1",
        }
        status, rec = svc.execute(doc)
        # recovery: release and confirm reachable again
        lab = NodeLabAdapter({"vpi-compute-01": url})
        lab.remove_isolation("vpi-compute-01", "quarantine_vlan")
        ver = HealthProbeVerify({"vpi-compute-01": url})
        recovered = ver.target_reachable("vpi-compute-01")
        return {"ok": status == 200 and rec.get("state") == "verified"
                and recovered,
                "evidence": [{"stage": "execute", "http": status,
                              "record": rec},
                             {"stage": "recovery",
                              "reachable": recovered}]}
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# negative regressions — must DENY, never silently pass
# ---------------------------------------------------------------------------

def negative_checks() -> list[dict]:
    out = []
    # expired approval
    gate = HardeningGate(FixtureAdapter(), secret=b"neg")
    prop, _ = gate.propose(
        {"candidate_id": "c1", "node_ref": "n1"},
        FixSpec(key="mqtt_tls", value=True),
        proposer_id="agent", proposer_role="agent")
    prop.created_at = time.time() - 99999  # force expiry
    ok, msg = gate.approve(prop.proposal_id, "cmd", "commander",
                           prop.fingerprint)
    out.append({"check": "expired_approval_denied",
                "pass": not ok and msg == "expired"})

    # self-approval (SoD)
    gate2 = HardeningGate(FixtureAdapter(), secret=b"neg2")
    p2, _ = gate2.propose(
        {"candidate_id": "c2", "node_ref": "n2"},
        FixSpec(key="mfa_required", value=True),
        proposer_id="agent-x", proposer_role="agent")
    ok, msg = gate2.approve(p2.proposal_id, "agent-x", "commander",
                            p2.fingerprint)
    out.append({"check": "self_approval_denied",
                "pass": not ok and "self" in msg})

    # fingerprint replay: same fp cannot approve twice
    gate3 = HardeningGate(FixtureAdapter(), secret=b"neg3")
    p3, _ = gate3.propose(
        {"candidate_id": "c3", "node_ref": "n3"},
        FixSpec(key="auto_updates", value=True),
        proposer_id="agent-y", proposer_role="agent")
    ok1, _ = gate3.approve(p3.proposal_id, "cmd-a", "commander",
                           p3.fingerprint)
    p4, _ = gate3.propose(
        {"candidate_id": "c4", "node_ref": "n3"},
        FixSpec(key="auto_updates", value=True),
        proposer_id="agent-z", proposer_role="agent")
    # replay p3's fingerprint on p4 -> denied
    ok2, msg2 = gate3.approve(p4.proposal_id, "cmd-b", "commander",
                              p3.fingerprint)
    out.append({"check": "fingerprint_replay_denied",
                "pass": ok1 and not ok2 and "fingerprint" in msg2})

    # failed verification -> FAILED, never silent success
    class LyingAdapter:
        def apply_fix(self, node_ref, fix):
            return {"ack": True}  # claims success
        def read_config(self, node_ref):
            return {}  # but config never changed
    gate4 = HardeningGate(LyingAdapter(), secret=b"neg4")
    p5, _ = gate4.propose(
        {"candidate_id": "c5", "node_ref": "n5"},
        FixSpec(key="fw_profile", value="restricted-egress"),
        proposer_id="agent-w", proposer_role="agent")
    gate4.approve(p5.proposal_id, "cmd", "commander", p5.fingerprint)
    ok, msg = gate4.execute(p5.proposal_id)
    out.append({"check": "verify_failure_is_failed",
                "pass": not ok and p5.state.value == "failed"
                and msg == "verify_failed"})

    # unapproved fix key refused at propose
    gate5 = HardeningGate(FixtureAdapter(), secret=b"neg5")
    p6, msg6 = gate5.propose(
        {"candidate_id": "c6", "node_ref": "n6"},
        FixSpec(key="root_password", value="hunter2"),
        proposer_id="agent", proposer_role="agent")
    out.append({"check": "non_allowlisted_fix_refused",
                "pass": p6 is None and msg6 == "fix_not_allowlisted"})
    return out
