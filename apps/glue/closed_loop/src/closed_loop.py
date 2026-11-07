"""GLUE-05: approval->containment->verification closed loop.

Chain: agent proposal -> Commander approval (role+scope) -> policy
(fingerprint, TTL, separation of duties, replay) -> durable outbox
(idempotent) -> lab executor -> INDEPENDENT verification -> scope
update -> team chat system post. Every stage audited; failures
surface as FAILED, never silent."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field


class Denied(Exception):
    pass


class VerifyFailed(Exception):
    pass


# ---------------- proposal + approval ---------------------------------

@dataclass
class Proposal:
    proposal_id: str
    action_type: str          # allowlisted: isolate_endpoint|disable_port|...
    target_id: str
    incident_id: str
    params: dict = field(default_factory=dict)
    proposed_by: str = "agent"
    created_at: float = field(default_factory=time.time)


ALLOWED_ACTIONS = {"isolate_endpoint", "disable_switch_port",
                   "quarantine_vlan", "block_egress"}
ALLOWED_TARGETS = {"lab-01", "lab-02", "switch-01", "puck-a-01"}
APPROVAL_TTL_S = 300.0


class ApprovalService:
    """Commander/admin approves; responder/observer/agent cannot.
    Separation of duties: approver != proposer."""

    APPROVER_ROLES = {"commander", "admin"}

    def __init__(self, clock=time.time):
        self.clock = clock
        self.approvals: dict[str, dict] = {}
        self.audit: list[dict] = []

    def approve(self, approver_id: str, approver_role: str,
                proposal: Proposal) -> str:
        if approver_role not in self.APPROVER_ROLES:
            self._audit("deny", approver_id, proposal.proposal_id,
                        "wrong_role")
            raise Denied(f"role {approver_role} cannot approve")
        if approver_id == proposal.proposed_by:
            self._audit("deny", approver_id, proposal.proposal_id,
                        "self_approval")
            raise Denied("separation of duties: self-approval")
        aid = f"appr-{uuid.uuid4().hex[:10]}"
        self.approvals[aid] = {
            "proposal": proposal, "approver": approver_id,
            "expires": self.clock() + APPROVAL_TTL_S,
            "fingerprint": self._fp(proposal), "consumed": False}
        self._audit("approve", approver_id, proposal.proposal_id,
                    {"approval_id": aid})
        return aid

    def consume(self, approval_id: str, action_fingerprint: str) -> dict:
        """Policy stage: valid, unexpired, unconsumed, fingerprint match."""
        a = self.approvals.get(approval_id)
        if a is None:
            raise Denied("unknown approval")
        if a["consumed"]:
            self._audit("deny", "system", approval_id, "replay")
            raise Denied("approval already consumed (replay)")
        if self.clock() > a["expires"]:
            raise Denied("approval expired")
        if not hmac.compare_digest(a["fingerprint"], action_fingerprint):
            self._audit("deny", "system", approval_id, "fingerprint_mismatch")
            raise Denied("action does not match approval")
        a["consumed"] = True
        return a

    def _fp(self, p: Proposal) -> str:
        material = json.dumps(
            {"t": p.action_type, "g": p.target_id, "i": p.incident_id,
             "p": p.params}, sort_keys=True)
        return hashlib.sha256(material.encode()).hexdigest()

    def fingerprint_for(self, p: Proposal) -> str:
        return self._fp(p)

    def _audit(self, op: str, actor: str, target: str, detail: str) -> None:
        self.audit.append({"at": self.clock(), "op": op, "actor": actor,
                           "target": target, "detail": detail})


# ---------------- outbox + executor ------------------------------------

@dataclass
class OutboxRecord:
    record_id: str
    approval_id: str
    proposal: Proposal
    state: str = "queued"     # queued|delivered|processed|failed
    attempts: int = 0


class Outbox:
    """Durable queue: idempotent on approval_id — redelivery of same
    approval does not re-execute."""

    def __init__(self):
        self.records: dict[str, OutboxRecord] = {}

    def enqueue(self, approval_id: str, proposal: Proposal) -> OutboxRecord:
        if approval_id in self.records:
            return self.records[approval_id]      # idempotent
        r = OutboxRecord(record_id=f"obx-{uuid.uuid4().hex[:8]}",
                         approval_id=approval_id, proposal=proposal)
        self.records[approval_id] = r
        return r

    def next_queued(self) -> OutboxRecord | None:
        return next((r for r in self.records.values()
                     if r.state == "queued"), None)

    def mark(self, approval_id: str, state: str) -> None:
        self.records[approval_id].state = state
        self.records[approval_id].attempts += 1


class LabExecutor:
    """Executes allowlisted actions against lab targets only. Returns
    stage-tagged result; API errors != success."""

    def __init__(self, lab_targets: set[str]):
        self.lab_targets = lab_targets
        self.executed: list[dict] = []

    def execute(self, proposal: Proposal) -> dict:
        if proposal.action_type not in ALLOWED_ACTIONS:
            raise Denied(f"action {proposal.action_type} not allowlisted")
        if proposal.target_id not in ALLOWED_TARGETS or \
                proposal.target_id not in self.lab_targets:
            raise Denied(f"target {proposal.target_id} not an owned lab asset")
        result = {"ok": True, "stage": "apply",
                  "detail": f"{proposal.action_type} on "
                            f"{proposal.target_id}",
                  "at": time.time()}
        self.executed.append(result)
        return result


class IndependentVerifier:
    """SEPARATE check — never trusts executor's self-report. Probes
    target reachability/state independently."""

    def __init__(self, probe):
        self.probe = probe      # callable(target_id)->bool reachable/isolated

    def verify(self, proposal: Proposal, exec_result: dict) -> dict:
        isolated = self.probe(proposal.target_id)
        if not exec_result.get("ok"):
            return {"verified": False, "reason": "executor reported failure",
                    "stage": "exec"}
        if not isolated:
            return {"verified": False,
                    "reason": "independent probe: target still reachable",
                    "stage": "verify"}
        return {"verified": True, "reason": "isolation confirmed",
                "stage": "verify"}


# ---------------- orchestrator -----------------------------------------

class ClosedLoop:
    def __init__(self, approvals: ApprovalService, outbox: Outbox,
                 executor: LabExecutor, verifier: IndependentVerifier,
                 clock=time.time):
        self.approvals = approvals
        self.outbox = outbox
        self.executor = executor
        self.verifier = verifier
        self.clock = clock
        self.timeline: list[dict] = []
        self.chat_posts: list[dict] = []

    def _tl(self, stage: str, detail: dict) -> None:
        self.timeline.append({"at": self.clock(), "stage": stage,
                              **detail})

    def submit(self, proposal: Proposal, approver_id: str,
               approver_role: str) -> str:
        """approval -> policy consume -> outbox enqueue. Returns
        approval_id. Denials audited + raised."""
        aid = self.approvals.approve(approver_id, approver_role, proposal)
        fp = self.approvals.fingerprint_for(proposal)
        self.approvals.consume(aid, fp)             # policy stage
        self.outbox.enqueue(aid, proposal)
        self._tl("approved_queued", {"approval_id": aid,
                                     "proposal": proposal.proposal_id})
        return aid

    def process_next(self) -> dict:
        """outbox -> executor -> independent verify -> scope+chat."""
        rec = self.outbox.next_queued()
        if rec is None:
            return {"state": "idle"}
        p = rec.proposal
        try:
            exec_res = self.executor.execute(p)
        except Denied as e:
            self.outbox.mark(rec.approval_id, "failed")
            self._tl("exec_denied", {"approval_id": rec.approval_id,
                                     "reason": str(e)})
            return {"state": "FAILED", "stage": "exec", "reason": str(e)}
        ver = self.verifier.verify(p, exec_res)
        if not ver["verified"]:
            self.outbox.mark(rec.approval_id, "failed")
            self._tl("verify_failed", {"approval_id": rec.approval_id,
                                       "reason": ver["reason"]})
            self.chat_posts.append(
                {"kind": "system", "body":
                 f"containment FAILED verification: {ver['reason']}",
                 "incident_id": p.incident_id})
            return {"state": "FAILED", "stage": ver["stage"],
                    "reason": ver["reason"]}
        self.outbox.mark(rec.approval_id, "processed")
        self._tl("verified", {"approval_id": rec.approval_id,
                              "target": p.target_id})
        self.chat_posts.append(
            {"kind": "system", "body":
             f"containment VERIFIED: {p.action_type} on {p.target_id}",
             "incident_id": p.incident_id,
             "links": {"approval_id": rec.approval_id}})
        return {"state": "VERIFIED", "approval_id": rec.approval_id,
                "target": p.target_id}
