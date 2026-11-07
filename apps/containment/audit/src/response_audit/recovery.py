"""Safe recovery / re-enable flow (issue #35).

Re-enabling a contained target is itself a privileged action: it needs
its own approval (recovery proposal != the original containment
approval), a scoped target, and INDEPENDENT verification that service
is restored — plus full audit of every stage. Rollback for the test
lab = revert isolation via the executor's revert path."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

from .audit import AuditLog


class RecoveryState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REVERTING = "reverting"
    VERIFYING = "verifying"
    RECOVERED = "recovered"
    RECOVERY_FAILED = "recovery_failed"
    DENIED = "denied"


@dataclass
class RecoveryRequest:
    recovery_id: str
    action_id: str               # the containment action being undone
    incident_id: str
    target_id: str
    reason: str
    requester_id: str
    state: RecoveryState = RecoveryState.PROPOSED
    approval: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class RecoveryDenied(Exception):
    pass


class RecoveryService:
    """Drives approved recoveries through revert + verify + audit."""

    APPROVER_ROLES = {"commander", "admin"}

    def __init__(self, audit: AuditLog):
        self.audit = audit
        self.requests: dict[str, RecoveryRequest] = {}

    # ---------------- propose + approve ----------------
    def propose(self, *, action_id: str, incident_id: str, target_id: str,
                reason: str, requester_id: str) -> RecoveryRequest:
        if len(reason) < 8:
            raise RecoveryDenied("recovery reason required (>=8 chars)")
        r = RecoveryRequest(
            recovery_id=f"rec-{uuid.uuid4().hex[:10]}",
            action_id=action_id, incident_id=incident_id,
            target_id=target_id, reason=reason, requester_id=requester_id)
        self.requests[r.recovery_id] = r
        self.audit.append(actor=requester_id, actor_role="operator",
                          operation="recover_propose",
                          entity_type="action", entity_id=action_id,
                          incident_id=incident_id, reason=reason,
                          after={"recovery_id": r.recovery_id,
                                 "target_id": target_id})
        return r

    def approve(self, recovery_id: str, *, approver_id: str,
                approver_role: str, approve: bool = True,
                reason: str = "") -> RecoveryRequest:
        r = self.requests.get(recovery_id)
        if r is None:
            raise RecoveryDenied("unknown recovery request")
        if approver_role not in self.APPROVER_ROLES:
            self.audit.append(actor=approver_id, actor_role=approver_role,
                              operation="recover_deny",
                              entity_type="action", entity_id=r.action_id,
                              incident_id=r.incident_id,
                              reason=f"role '{approver_role}' cannot approve "
                                     f"recovery: {reason}")
            r.state = RecoveryState.DENIED
            raise RecoveryDenied(f"role '{approver_role}' cannot approve recovery")
        if approver_id == r.requester_id:
            self.audit.append(actor=approver_id, actor_role=approver_role,
                              operation="recover_deny",
                              entity_type="action", entity_id=r.action_id,
                              incident_id=r.incident_id,
                              reason="self-approval of recovery denied")
            r.state = RecoveryState.DENIED
            raise RecoveryDenied("self-approval of recovery denied")
        r.approval = {"approver_id": approver_id, "role": approver_role,
                      "decision": "approve" if approve else "deny",
                      "reason": reason, "at": time.time()}
        r.state = RecoveryState.APPROVED if approve else RecoveryState.DENIED
        self.audit.append(actor=approver_id, actor_role=approver_role,
                          operation="recover_approve" if approve else "recover_deny",
                          entity_type="action", entity_id=r.action_id,
                          incident_id=r.incident_id, reason=reason,
                          after={"recovery_id": recovery_id,
                                 "decision": r.approval["decision"]})
        if not approve:
            raise RecoveryDenied("recovery denied by approver")
        return r

    # ---------------- execute recovery ----------------
    def execute(self, recovery_id: str, *, revert_fn, verify_fn) -> RecoveryRequest:
        """revert_fn(target_id, action_id) -> api result;
        verify_fn(target_id) -> bool restored."""
        r = self.requests.get(recovery_id)
        if r is None or r.state != RecoveryState.APPROVED:
            raise RecoveryDenied("recovery not approved")
        r.state = RecoveryState.REVERTING
        self.audit.append(actor="executor", actor_role="executor",
                          operation="recover_revert",
                          entity_type="action", entity_id=r.action_id,
                          incident_id=r.incident_id,
                          reason=r.reason,
                          before={"state": "contained"})
        try:
            api = revert_fn(r.target_id, r.action_id)
        except Exception as e:
            r.state = RecoveryState.RECOVERY_FAILED
            self.audit.append(actor="executor", actor_role="executor",
                              operation="recover_failed",
                              entity_type="action", entity_id=r.action_id,
                              incident_id=r.incident_id,
                              reason=str(e),
                              verification={"restored": False})
            return r
        r.state = RecoveryState.VERIFYING
        restored = bool(verify_fn(r.target_id))
        self.audit.append(actor="verifier", actor_role="executor",
                          operation="recover_verify",
                          entity_type="action", entity_id=r.action_id,
                          incident_id=r.incident_id,
                          verification={"restored": restored,
                                        "method": "independent_probe"},
                          after={"api_response": api})
        r.state = (RecoveryState.RECOVERED if restored
                   else RecoveryState.RECOVERY_FAILED)
        self.audit.append(actor="system", actor_role="system",
                          operation="recover_result",
                          entity_type="action", entity_id=r.action_id,
                          incident_id=r.incident_id,
                          reason=r.reason,
                          after={"state": r.state.value})
        return r
