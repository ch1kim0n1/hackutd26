"""Deterministic flow-decision engine — issue #105.

Pure policy evaluation: same (flow, policy, clock) -> same decision.
The engine NEVER enforces anything and NEVER logs by itself — callers
compose engine.evaluate() with DecisionLog.append() (see __init__ for
the intended wiring). Enforcement is a separate component (#106).
"""
from __future__ import annotations

import time
import uuid

from .models import (
    DefaultAction,
    FlowDecision,
    FlowDecisionKind,
    FlowPolicy,
    FlowTuple,
    FlowValidationError,
    utc_now_iso,
)


class DecisionEngine:
    """Evaluates FlowTuples against a FlowPolicy.

    Ordering contract: rules are evaluated in declared order; the
    FIRST match wins. Unmatched flows take the policy's explicit
    default_action — DENY -> block (fail-closed), MONITOR -> allow
    with rule_id=None so the record still shows it bypassed rules.
    """

    def __init__(self, policy: FlowPolicy):
        if not isinstance(policy, FlowPolicy):
            raise TypeError("policy must be a FlowPolicy")
        self.policy = policy

    def evaluate(self, flow: FlowTuple, *, trace_id: str = "",
                 now: float | None = None) -> FlowDecision:
        """Return the policy outcome for `flow`. Raises
        FlowValidationError on malformed input — never guesses."""
        flow.validate()
        if len(trace_id) > 128:
            raise FlowValidationError("trace_id exceeds 128 chars")
        ts = time.time() if now is None else now

        for rule in self.policy.rules:
            if rule.match.matches(flow):
                return self._decide(
                    flow,
                    decision=rule.action,
                    reason=rule.reason or f"matched rule '{rule.rule_id}'",
                    rule_id=rule.rule_id,
                    redirect_to=rule.redirect_to,
                    ttl_s=rule.ttl_s if rule.ttl_s is not None
                    else self.policy.default_ttl_s,
                    trace_id=trace_id, ts=ts)

        if self.policy.default_action is DefaultAction.DENY:
            return self._decide(
                flow, decision=FlowDecisionKind.BLOCK,
                reason="no matching rule; default deny",
                rule_id=None, redirect_to=None,
                ttl_s=self.policy.default_ttl_s,
                trace_id=trace_id, ts=ts)
        return self._decide(
            flow, decision=FlowDecisionKind.ALLOW,
            reason="no matching rule; default monitor",
            rule_id=None, redirect_to=None,
            ttl_s=self.policy.default_ttl_s,
            trace_id=trace_id, ts=ts)

    # ---------------- internals ----------------
    def _decide(self, flow: FlowTuple, *, decision: FlowDecisionKind,
                reason: str, rule_id: str | None,
                redirect_to, ttl_s: float, trace_id: str,
                ts: float) -> FlowDecision:
        return FlowDecision(
            decision_id=f"fdec-{uuid.uuid4().hex[:12]}",
            flow=flow,
            decision=decision,
            reason=reason,
            policy_id=self.policy.policy_id,
            policy_version=self.policy.version,
            rule_id=rule_id,
            redirect_to=redirect_to,
            ttl_s=ttl_s,
            decided_at=utc_now_iso(ts),
            trace_id=trace_id,
            provenance=flow.provenance,
        )
