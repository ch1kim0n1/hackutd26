"""Lab adapters — the ONLY components holding lab credentials.

- LabAdapter: apply containment change to an OWNED lab target.
- VerifyAdapter: INDEPENDENT probe of resulting state — separate code
  path, separate (read-only) credentials where possible. An API '200'
  from apply is never treated as verification (docs/08 threat 3).

MockLabAdapter simulates a firewall rule + endpoint reachability for
tests. Real deployment: SSH/REST to the dedicated lab firewall/switch
with lab-only credentials — executor holds NO database/admin creds."""
from __future__ import annotations

from typing import Protocol


class LabUnavailable(RuntimeError):
    pass


class LabAdapter(Protocol):
    def apply_isolation(self, target_id: str, action_type: str) -> dict: ...
    def remove_isolation(self, target_id: str, action_type: str) -> dict: ...


class VerifyAdapter(Protocol):
    def target_reachable(self, target_id: str) -> bool: ...
    def isolation_effective(self, target_id: str, action_type: str) -> bool: ...


class MockLabAdapter:
    """Simulated lab: firewall rules + endpoint host state."""

    def __init__(self, fail_apply: bool = False, lie_about_success: bool = False):
        self.rules: dict[str, str] = {}       # target -> action_type isolated
        self.endpoint_up: dict[str, bool] = {}  # target -> reachable
        self.fail_apply = fail_apply
        self.lie_about_success = lie_about_success  # API says ok, does nothing
        self.calls: list[dict] = []

    def apply_isolation(self, target_id: str, action_type: str) -> dict:
        self.calls.append({"op": "apply", "target": target_id,
                           "type": action_type})
        if self.fail_apply:
            return {"ok": False, "error": "simulated adapter failure"}
        if not self.lie_about_success:
            self.rules[target_id] = action_type
            self.endpoint_up[target_id] = False   # actually isolated
        # lie_about_success: claims ok but changes nothing
        return {"ok": True, "rule_id": f"rule-{target_id}"}

    def remove_isolation(self, target_id: str, action_type: str) -> dict:
        self.calls.append({"op": "remove", "target": target_id,
                           "type": action_type})
        self.rules.pop(target_id, None)
        self.endpoint_up[target_id] = True
        return {"ok": True}


class MockVerifyAdapter:
    """Independent probe — reads endpoint_up state, NOT the API response.
    In production this is a separate connectivity check (ping/HTTP probe
    from a different vantage) with its own credentials."""

    def __init__(self, lab: MockLabAdapter):
        self.lab = lab
        self.probes: list[str] = []

    def target_reachable(self, target_id: str) -> bool:
        self.probes.append(target_id)
        return self.lab.endpoint_up.get(target_id, True)

    def isolation_effective(self, target_id: str, action_type: str) -> bool:
        self.probes.append(f"{target_id}:{action_type}")
        return target_id in self.lab.rules
