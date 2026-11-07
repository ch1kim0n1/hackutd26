"""HardenedAgent — wraps an investigation agent's registry with
ToolGuard on dispatch and ModelOutputGuard on assessment writes.

Trust boundaries enforced regardless of model behavior:
- every tool call passes ToolGuard (allowlist + authority denylist +
  budgets + loop detection) BEFORE reaching the real dispatcher
- append_agent_assessment payloads are schema + citation + claim
  validated BEFORE being recorded — violations are rejected, not stored
- sensor-derived strings can be fenced via UntrustedText upstream"""
from __future__ import annotations

from dataclasses import dataclass, field

from .guard import ToolGuard
from .output_guard import ModelOutputGuard


@dataclass
class HardenedResult:
    inner_result: object
    assessment_accepted: bool
    assessment_violations: list[str]
    denied_tool_calls: list[dict]
    guard_trace: list[dict] = field(default_factory=list)


class HardenedAgent:
    def __init__(self, inner_agent, tool_guard: ToolGuard,
                 output_guard: ModelOutputGuard):
        self.inner = inner_agent
        self.tool_guard = tool_guard
        self.output_guard = output_guard
        self.denied_tool_calls: list[dict] = []
        self.rejected_assessments: list[dict] = []
        self._installed = False

    def install(self) -> None:
        """Monkey-patch the inner registry's dispatch + assessment sink.
        Call once after constructing the inner agent."""
        if self._installed:
            return
        reg = self.inner.registry
        original_call = reg.call
        guard = self.tool_guard
        denied = self.denied_tool_calls

        class _Guarded:
            def __init__(self):
                self.ok = False
                self.tool = ""
                self.data = None
                self.error = ""
                self.denied = True

        def guarded_call(name, arguments):
            decision = guard.check(name, arguments)
            if not decision.allowed:
                denied.append({"tool": name, "reason": decision.reason})
                r = _Guarded()
                r.tool = name
                r.error = decision.reason
                return r
            # wrap append_agent_assessment so its payload is validated
            if name == "append_agent_assessment":
                verdict = self.output_guard.check_assessment(arguments)
                if not verdict.ok:
                    self.rejected_assessments.append(
                        {"args": arguments, "violations": verdict.violations})
                    r = _Guarded()
                    r.tool = name
                    r.error = "assessment rejected: " + "; ".join(verdict.violations)
                    return r
            return original_call(name, arguments)

        reg.call = guarded_call
        self._installed = True
        self._original_call = original_call

    def investigate(self, incident_brief: str) -> HardenedResult:
        self.install()
        result = self.inner.investigate(incident_brief)
        degraded = getattr(result, "degraded", False)
        return HardenedResult(
            inner_result=result,
            assessment_accepted=not self.rejected_assessments and not degraded,
            assessment_violations=(self.rejected_assessments[-1]["violations"]
                                   if self.rejected_assessments else []),
            denied_tool_calls=list(self.denied_tool_calls),
            guard_trace=list(self.tool_guard.trace),
        )
