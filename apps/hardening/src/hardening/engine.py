"""Policy-gated preventive hardening (#104).

Posture candidates -> bounded config fixes -> human approval (SoD:
proposer != approver) -> executor apply -> INDEPENDENT verification
(re-read config, not executor ack) -> verified|failed. API ack never
counts as verified. TTL + fingerprint + replay denial, mirroring
apps/containment/policy rules.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol


class HState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    EXECUTING = "executing"
    VERIFIED = "verified"
    FAILED = "failed"


# bounded fix allowlist: only these config keys may be hardened
ALLOWED_FIXES = {
    "ssh_password_auth": {"allowed_values": [False],
                          "description": "disable SSH password auth"},
    "auto_updates": {"allowed_values": [True],
                     "description": "enable auto updates"},
    "snmp_community_write": {"allowed_values": [False],
                             "description": "disable SNMP write community"},
    "mqtt_tls": {"allowed_values": [True],
                 "description": "require MQTT TLS"},
    "mfa_required": {"allowed_values": [True],
                     "description": "require MFA on management"},
    "fw_profile": {"allowed_values": ["restricted-egress"],
                   "description": "restrict egress firewall profile"},
}

ROLES = {"commander", "responder", "agent", "observer", "admin"}


@dataclass
class FixSpec:
    key: str
    value: object

    @property
    def valid(self) -> bool:
        spec = ALLOWED_FIXES.get(self.key)
        return bool(spec and self.value in spec["allowed_values"])


@dataclass
class HardeningProposal:
    proposal_id: str
    candidate_id: str
    node_ref: str
    fix: FixSpec
    reason: str
    proposer_id: str
    proposer_role: str
    created_at: float
    ttl_s: float = 900.0
    fingerprint: str = ""
    state: HState = HState.PROPOSED
    approvals: list = field(default_factory=list)

    @property
    def expires_at(self) -> float:
        return self.created_at + self.ttl_s

    def is_expired(self, now: Optional[float] = None) -> bool:
        return (time.time() if now is None else now) > self.expires_at


@dataclass
class NodeConfigAdapter(Protocol):
    """Apply + independently read node config. Live impl plugs into
    #101 service control plane; fixture impl for tests."""
    def apply_fix(self, node_ref: str, fix: FixSpec) -> dict: ...
    def read_config(self, node_ref: str) -> dict: ...


class FixtureAdapter:
    """In-memory node config store; apply mutates, read verifies."""

    def __init__(self, configs: Optional[dict[str, dict]] = None):
        self.configs = configs or {}
        self.applied: list[tuple[str, FixSpec]] = []

    def apply_fix(self, node_ref: str, fix: FixSpec) -> dict:
        self.applied.append((node_ref, fix))
        self.configs.setdefault(node_ref, {})[fix.key] = fix.value
        return {"ack": True, "node": node_ref, "key": fix.key}

    def read_config(self, node_ref: str) -> dict:
        return dict(self.configs.get(node_ref, {}))


def fingerprint(proposal: HardeningProposal, secret: bytes) -> str:
    blob = json.dumps({
        "proposal_id": proposal.proposal_id,
        "candidate_id": proposal.candidate_id,
        "node_ref": proposal.node_ref,
        "fix": {"key": proposal.fix.key, "value": proposal.fix.value},
        "created_at": proposal.created_at,
    }, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hmac.new(secret, blob, hashlib.sha256).hexdigest()


class HardeningGate:
    """Policy gate: propose -> approve (SoD) -> execute -> verify."""

    def __init__(self, adapter: NodeConfigAdapter, secret: bytes = b"lab",
                 approver_roles: tuple = ("commander", "admin")):
        self.adapter = adapter
        self.secret = secret
        self.approver_roles = set(approver_roles)
        self.proposals: dict[str, HardeningProposal] = {}
        self._used_fingerprints: set[str] = set()

    # -- propose -----------------------------------------------------------

    def propose(self, candidate: dict, fix: FixSpec,
                proposer_id: str, proposer_role: str,
                reason: str = "") -> tuple[Optional[HardeningProposal], str]:
        if proposer_role not in ROLES:
            return None, "unknown_role"
        if not fix.valid:
            return None, "fix_not_allowlisted"
        cand_id = candidate.get("candidate_id", "")
        node = candidate.get("node_ref", "")
        if not cand_id or not node:
            return None, "bad_candidate"
        pid = "hp-" + hashlib.sha256(
            f"{cand_id}|{node}|{fix.key}|{fix.value}".encode()).hexdigest()[:12]
        if pid in self.proposals:
            return self.proposals[pid], "duplicate"
        p = HardeningProposal(
            proposal_id=pid, candidate_id=cand_id, node_ref=node,
            fix=fix, reason=reason or candidate.get("title", ""),
            proposer_id=proposer_id, proposer_role=proposer_role,
            created_at=time.time(),
        )
        p.fingerprint = fingerprint(p, self.secret)
        self.proposals[pid] = p
        return p, "ok"

    # -- approve -------------------------------------------------------------

    def approve(self, proposal_id: str, approver_id: str,
                approver_role: str, fp: str,
                now: Optional[float] = None) -> tuple[bool, str]:
        now = now or time.time()
        p = self.proposals.get(proposal_id)
        if p is None:
            return False, "unknown_proposal"
        if p.state != HState.PROPOSED:
            return False, f"bad_state:{p.state.value}"
        if p.is_expired(now):
            p.state = HState.EXPIRED
            return False, "expired"
        if approver_role not in self.approver_roles:
            return False, "role_cannot_approve"
        if approver_id == p.proposer_id:
            return False, "self_approval_denied"          # SoD
        if fp != p.fingerprint or fp in self._used_fingerprints:
            return False, "fingerprint_mismatch_or_replay"
        p.approvals.append({"by": approver_id, "role": approver_role,
                            "fp": fp, "at": now})
        self._used_fingerprints.add(fp)
        p.state = HState.APPROVED
        return True, "approved"

    # -- execute + verify ----------------------------------------------------

    def execute(self, proposal_id: str) -> tuple[bool, str]:
        p = self.proposals.get(proposal_id)
        if p is None:
            return False, "unknown_proposal"
        if p.state != HState.APPROVED:
            return False, f"bad_state:{p.state.value}"
        if p.is_expired():
            p.state = HState.EXPIRED
            return False, "expired"
        p.state = HState.EXECUTING
        ack = self.adapter.apply_fix(p.node_ref, p.fix)
        if not ack.get("ack"):
            p.state = HState.FAILED
            return False, "apply_failed"
        # independent verification: re-read config, compare value
        live = self.adapter.read_config(p.node_ref)
        if live.get(p.fix.key) == p.fix.value:
            p.state = HState.VERIFIED
            return True, "verified"
        p.state = HState.FAILED
        return False, "verify_failed"
