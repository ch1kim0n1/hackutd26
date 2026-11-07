"""Approval-bound, allowlisted containment policy service (issue #33).

docs/08 rules for contained actions + threat 7 (race/retry):
- scope-bound proposal: incident_id + target allowlist + finite action
  types + TTL + reason required
- fingerprint binds action hash + target + TTL + initiator — approvals
  must present the matching fingerprint (replay/forgery resistant)
- separation of duties: approver != proposer
- role checks server-side: proposer in PROPOSER_ROLES, approver in
  APPROVER_ROLES
- monotonic action state; expired proposals can't be approved;
  duplicate approval fingerprints rejected"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from .models import (
    ActionProposal,
    ActionState,
    ActionType,
    Approval,
    PolicyResult,
    PROPOSER_ROLES,
    APPROVER_ROLES,
    Role,
)

DEFAULT_TTL_S = 300.0
MAX_TTL_S = 900.0


class ContainmentPolicy:
    def __init__(self, allowed_targets: set[str],
                 allowed_incidents: set[str] | None = None,
                 fingerprint_secret: bytes = b"dev-only-not-secret",
                 clock=time.time):
        self.allowed_targets = set(allowed_targets)
        self.allowed_incidents = allowed_incidents  # None = any incident
        self.secret = fingerprint_secret
        self.clock = clock
        self.proposals: dict[str, ActionProposal] = {}
        self.approvals: list[Approval] = []
        self._used_fingerprints: set[str] = set()

    # ---------------- fingerprint ----------------
    def fingerprint_for(self, p: ActionProposal) -> str:
        """docs/08: approval bound to action hash + target + TTL + initiator."""
        material = json.dumps({
            "proposal_id": p.proposal_id,
            "incident_id": p.incident_id,
            "action_type": p.action_type.value,
            "target_id": p.target_id,
            "proposer_id": p.proposer_id,
            "ttl_s": p.ttl_s,
            "created_at": p.created_at,
        }, sort_keys=True).encode()
        return hmac.new(self.secret, material, hashlib.sha256).hexdigest()

    # ---------------- propose ----------------
    def propose(self, *, incident_id: str, action_type: str, target_id: str,
                reason: str, proposer_id: str, proposer_role: Role | str,
                ttl_s: float = DEFAULT_TTL_S,
                scope: dict | None = None) -> PolicyResult:
        try:
            role = Role(proposer_role)
            atype = ActionType(action_type)
        except ValueError as e:
            return PolicyResult(False, f"invalid enum: {e}")
        if role not in PROPOSER_ROLES:
            return PolicyResult(False, f"role '{role.value}' may not propose")
        if self.allowed_incidents is not None and incident_id not in self.allowed_incidents:
            return PolicyResult(False, "incident outside policy scope")
        if target_id not in self.allowed_targets:
            return PolicyResult(False, f"target '{target_id}' not in lab allowlist")
        if not reason or len(reason) < 8:
            return PolicyResult(False, "reason required (>=8 chars)")
        if not (0 < ttl_s <= MAX_TTL_S):
            return PolicyResult(False, f"ttl_s must be in (0,{MAX_TTL_S}]")
        now = self.clock()
        p = ActionProposal(
            proposal_id=f"act-{uuid.uuid4().hex[:10]}",
            incident_id=incident_id, action_type=atype, target_id=target_id,
            reason=reason, proposer_id=proposer_id, proposer_role=role,
            created_at=now, ttl_s=ttl_s, scope=scope or {})
        p.fingerprint = self.fingerprint_for(p)
        self.proposals[p.proposal_id] = p
        return PolicyResult(True, "proposed", proposal=p)

    # ---------------- approve / deny ----------------
    def decide(self, *, proposal_id: str, approver_id: str,
               approver_role: Role | str, decision: str,
               fingerprint: str, reason: str = "") -> PolicyResult:
        try:
            role = Role(approver_role)
        except ValueError:
            return PolicyResult(False, "invalid approver role")
        if role not in APPROVER_ROLES:
            return PolicyResult(False, f"role '{role.value}' may not approve/deny")
        p = self.proposals.get(proposal_id)
        if p is None:
            return PolicyResult(False, "unknown proposal")
        if p.state != ActionState.PROPOSED:
            return PolicyResult(False, f"proposal state '{p.state.value}' "
                                f"is not decidable")
        now = self.clock()
        if p.is_expired(now):
            p.state = ActionState.EXPIRED
            return PolicyResult(False, "proposal expired", proposal=p)
        # fingerprint must match exactly — binds action+target+TTL+initiator.
        # Recompute from CURRENT fields so tampering proposal contents
        # (target/type/ttl) is detected, not just arg forgery.
        expected = self.fingerprint_for(p)
        if p.fingerprint != expected or \
                not hmac.compare_digest(fingerprint, expected):
            return PolicyResult(False, "fingerprint mismatch — approval not "
                                "bound to this exact proposal", proposal=p)
        # replay: same fingerprint already decided
        if fingerprint in self._used_fingerprints:
            return PolicyResult(False, "duplicate approval fingerprint "
                                "(replay rejected)", proposal=p)
        # separation of duties
        if approver_id == p.proposer_id:
            return PolicyResult(False, "self-approval denied "
                                "(separation of duties)", proposal=p)
        dec = decision.lower()
        if dec not in ("approve", "deny"):
            return PolicyResult(False, "decision must be approve|deny")
        self._used_fingerprints.add(fingerprint)
        appr = Approval(
            approval_id=f"appr-{uuid.uuid4().hex[:10]}",
            proposal_id=proposal_id, approver_id=approver_id,
            approver_role=role, decision=dec, fingerprint=fingerprint,
            decided_at=now, reason=reason)
        self.approvals.append(appr)
        if dec == "approve":
            p.state = ActionState.APPROVED
            return PolicyResult(True, "approved", proposal=p, approval=appr)
        p.state = ActionState.DENIED
        return PolicyResult(True, "denied-by-approver", proposal=p, approval=appr)

    # ---------------- executor-facing ----------------
    def approved_actions(self) -> list[ActionProposal]:
        """Actions an executor may pick up — approved, unexpired."""
        now = self.clock()
        return [p for p in self.proposals.values()
                if p.state == ActionState.APPROVED and not p.is_expired(now)]

    def mark_state(self, proposal_id: str, state: ActionState,
                   allowed_from: set[ActionState] | None = None) -> bool:
        """Monotonic-ish state transitions for the executor/audit."""
        p = self.proposals.get(proposal_id)
        if p is None:
            return False
        if allowed_from and p.state not in allowed_from:
            return False
        p.state = state
        return True
