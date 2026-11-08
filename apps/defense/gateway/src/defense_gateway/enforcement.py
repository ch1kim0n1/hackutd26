"""Simulated enforcement point — issue #105.

Stand-in for the real lab proxy/firewall (#106). It applies NOTHING to
any network: given a FlowDecision it emits an EnforcementOutcome
receipt recording what a real enforcer WOULD do, always stamped
enforcement="simulated". This keeps the policy-outcome vs
enforcement-point separation explicit and testable — a decision record
alone is never proof of enforcement.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from .models import (
    EnforcementStatus,
    FlowDecision,
    FlowDecisionKind,
    utc_now_iso,
)


@dataclass(frozen=True)
class EnforcementOutcome:
    """Receipt that a (simulated) enforcement point processed a
    decision. `result` mirrors the decision; `enforcement` stays
    SIMULATED until the #106 verified path exists."""
    outcome_id: str
    decision_id: str
    flow_id: str
    result: str                     # allow | block | redirect
    redirect_target: str | None     # "node/service" when result=redirect
    trace_id: str
    at: str
    enforcement: EnforcementStatus = EnforcementStatus.SIMULATED
    schema_version: int = 1

    def as_record(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "outcome_id": self.outcome_id,
            "decision_id": self.decision_id,
            "flow_id": self.flow_id,
            "result": self.result,
            "redirect_target": self.redirect_target,
            "trace_id": self.trace_id,
            "at": self.at,
            "enforcement": self.enforcement.value,
        }


class SimulatedEnforcementPoint:
    """Consumes FlowDecisions and produces simulated receipts.
    Stateless, lab-only, no sockets, no firewall rules, no packets."""

    def apply(self, decision: FlowDecision, *,
              now: float | None = None) -> EnforcementOutcome:
        if not isinstance(decision, FlowDecision):
            raise TypeError("apply() requires a FlowDecision")
        result = decision.decision.value
        target = None
        if decision.decision is FlowDecisionKind.REDIRECT and decision.redirect_to:
            target = str(decision.redirect_to)
        return EnforcementOutcome(
            outcome_id=f"enf-{uuid.uuid4().hex[:12]}",
            decision_id=decision.decision_id,
            flow_id=decision.flow.flow_id,
            result=result,
            redirect_target=target,
            trace_id=decision.trace_id,
            at=utc_now_iso(now),
        )
