"""Executor models — docs/08 threat 3 + docs/04 action states.

proposed/authorized/started/verified are recorded SEPARATELY: an API
ack is never verification. 'verified' requires the independent probe."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecState(str, Enum):
    QUEUED = "queued"              # approved action awaiting executor
    STARTED = "started"            # adapter.apply called
    API_ACKED = "api_acked"        # adapter returned success — NOT proof
    VERIFIED = "verified"          # independent probe confirms effect
    FAILED = "failed"              # apply error OR verification failed
    SKIPPED_DUPLICATE = "skipped_duplicate"
    REJECTED_UNAPPROVED = "rejected_unapproved"


@dataclass
class ExecutionRecord:
    record_id: str
    action_id: str               # proposal_id from policy service
    incident_id: str
    action_type: str
    target_id: str
    state: ExecState
    states_history: list[dict] = field(default_factory=list)
    api_response: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def transition(self, state: ExecState, **detail) -> None:
        self.state = state
        self.states_history.append(
            {"state": state.value, "at": time.time(), **detail})
        self.updated_at = time.time()


@dataclass
class OutboxItem:
    """One approved action delivered to the executor."""
    action_id: str
    incident_id: str
    action_type: str
    target_id: str
    reason: str
    approved_by: str
    approval_id: str
    expires_at: float
    fingerprint: str
    payload: dict = field(default_factory=dict)

    @classmethod
    def from_proposal(cls, p, approval) -> "OutboxItem":
        return cls(
            action_id=p.proposal_id, incident_id=p.incident_id,
            action_type=p.action_type.value, target_id=p.target_id,
            reason=p.reason, approved_by=approval.approver_id,
            approval_id=approval.approval_id,
            expires_at=p.expires_at, fingerprint=p.fingerprint,
            payload=dict(p.scope))

    def new_record(self) -> ExecutionRecord:
        return ExecutionRecord(
            record_id=f"exec-{uuid.uuid4().hex[:10]}",
            action_id=self.action_id, incident_id=self.incident_id,
            action_type=self.action_type, target_id=self.target_id,
            state=ExecState.QUEUED)
