"""Containment policy models — docs/04 action/approval contracts +
docs/08 rules-for-contained-actions."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    ADMIN = "admin"
    COMMANDER = "commander"
    RESPONDER = "responder"
    OBSERVER = "observer"
    AGENT = "agent"
    DEVICE = "device"
    EXECUTOR = "executor"


# Who may PROPOSE containment: agent + humans investigating.
PROPOSER_ROLES = {Role.AGENT, Role.RESPONDER, Role.COMMANDER, Role.ADMIN}
# Who may APPROVE: commander/admin only — separation from proposer.
APPROVER_ROLES = {Role.COMMANDER, Role.ADMIN}


class ActionType(str, Enum):
    ISOLATE_ENDPOINT = "isolate_endpoint"       # firewall/switch quarantine
    DISABLE_AP = "disable_ap"                    # owned lab AP off
    DISABLE_SWITCH_PORT = "disable_switch_port"  # owned switch port
    REVOKE_CREDENTIAL = "revoke_credential"      # scoped cred rotation
    QUARANTINE_VLAN = "quarantine_vlan"
    # NOTE: no freeform/shell/network types exist — finite enum only.


class ActionState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    EXECUTING = "executing"
    VERIFIED = "verified"
    FAILED = "failed"
    REVERTING = "reverting"
    REVERTED = "reverted"


@dataclass
class ActionProposal:
    proposal_id: str
    incident_id: str
    action_type: ActionType
    target_id: str
    reason: str
    proposer_id: str
    proposer_role: Role
    created_at: float
    ttl_s: float
    fingerprint: str = ""
    state: ActionState = ActionState.PROPOSED
    scope: dict[str, Any] = field(default_factory=dict)

    @property
    def expires_at(self) -> float:
        return self.created_at + self.ttl_s

    def is_expired(self, now: float | None = None) -> bool:
        return (time.time() if now is None else now) > self.expires_at


@dataclass
class Approval:
    approval_id: str
    proposal_id: str
    approver_id: str
    approver_role: Role
    decision: str                    # "approve" | "deny"
    fingerprint: str                 # must equal proposal fingerprint
    decided_at: float
    reason: str = ""


@dataclass
class PolicyResult:
    ok: bool
    reason: str
    proposal: ActionProposal | None = None
    approval: Approval | None = None
