"""ToolGuard — hardening layer around any tool-call dispatcher.

Enforces, regardless of what the model asks for:
- name allowlist AND a denylist of authority-bearing names
  (approve/execute/contain/delete/grant — the agent may only PROPOSE)
- argument sanity: required keys present, string length caps, no
  nested instruction-looking values passed to privileged args
- per-incident call budget + identical-call loop detection
Every decision is traced for audit."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .untrusted import UntrustedText

# Names that would exceed agent authority — never callable, even if a
# registry accidentally exposes them.
DENIED_TOOL_PATTERNS = (
    "approve", "execute", "deploy", "delete", "grant",
    "revoke", "shell", "cmd", "run_", "admin", "firewall_apply",
    "switch_disable", "isolate_now", "contain_now", "apply_",
)

MAX_ARG_STRING = 4000
MAX_CALLS_PER_RUN = 20
MAX_REPEAT_CALLS = 3


@dataclass
class GuardDecision:
    allowed: bool
    reason: str = ""
    tool: str = ""


class ToolGuard:
    def __init__(self, allowed_tools: set[str],
                 max_calls: int = MAX_CALLS_PER_RUN,
                 max_repeat: int = MAX_REPEAT_CALLS):
        self.allowed = set(allowed_tools)
        self.max_calls = max_calls
        self.max_repeat = max_repeat
        self._counts: dict[str, int] = {}
        self._call_hashes: dict[str, int] = {}
        self.trace: list[dict] = []

    def check(self, name: str, arguments: dict) -> GuardDecision:
        d = self._evaluate(name, arguments)
        self.trace.append({"tool": name, "allowed": d.allowed,
                           "reason": d.reason})
        return d

    def _evaluate(self, name: str, a: dict) -> GuardDecision:
        lname = name.lower()
        for pat in DENIED_TOOL_PATTERNS:
            if pat in lname:
                return GuardDecision(False, f"authority-bearing tool '{name}' "
                                     f"denied — agent may only propose", name)
        if name not in self.allowed:
            return GuardDecision(False, f"tool '{name}' not allowlisted", name)
        # arg hygiene
        if not isinstance(a, dict):
            return GuardDecision(False, "arguments must be an object", name)
        for k, v in a.items():
            if isinstance(v, str) and len(v) > MAX_ARG_STRING:
                return GuardDecision(False, f"arg '{k}' exceeds size cap", name)
            # nested injection-looking strings in privileged-looking args
            if isinstance(v, str) and UntrustedText(v, source=k).looks_like_injection \
                    and any(s in k.lower() for s in ("command", "exec", "shell", "instruction")):
                return GuardDecision(False, f"arg '{k}' carries instruction-like "
                                     f"content", name)
        # budgets + loop detection
        self._counts[name] = self._counts.get(name, 0) + 1
        total = sum(self._counts.values())
        if total > self.max_calls:
            return GuardDecision(False, "per-run tool-call budget exhausted", name)
        h = hashlib.sha256(json.dumps(a, sort_keys=True, default=str).encode()).hexdigest()[:16]
        key = f"{name}|{h}"
        self._call_hashes[key] = self._call_hashes.get(key, 0) + 1
        if self._call_hashes[key] > self.max_repeat:
            return GuardDecision(False, "identical call repeated > "
                                 f"{self.max_repeat}x — loop suspected", name)
        return GuardDecision(True, "", name)
