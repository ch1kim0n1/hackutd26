"""Bounded tool registry — exactly the docs/05 allowlist.

Nine tools, strict argument schemas, scope-checked dispatch.
NO shell, NO arbitrary network, NO approve/execute-containment tools —
the agent can only propose (docs/05, docs/08 trust matrix)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


class ToolDenied(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class ToolContext:
    """Per-run scope: which incident/zones/devices this agent may touch."""
    incident_id: str
    allowed_zones: set[str] = field(default_factory=set)
    allowed_waypoints: set[str] = field(default_factory=set)
    allowed_devices: set[str] = field(default_factory=set)


@dataclass
class ToolResult:
    ok: bool
    tool: str
    data: Any = None
    error: str = ""
    denied: bool = False


def _req(args: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in args]
    if missing:
        raise ToolDenied(f"missing required args: {missing}")


class ToolRegistry:
    """Allowlisted tools bound to backend callables."""

    def __init__(self, ctx: ToolContext, backends: dict[str, Callable]):
        self.ctx = ctx
        self.backends = backends
        self.calls: list[dict] = []          # decision trace
        self._specs = self._build_specs()

    # ---------------- schema exposure ----------------
    def specs(self):
        return list(self._specs.values())

    def _build_specs(self) -> dict:
        S = lambda props, req: {"type": "object", "properties": props,
                                "required": req, "additionalProperties": False}
        return {
            "get_recent_observations": {
                "name": "get_recent_observations",
                "description": "Recent sensor observations for this incident scope",
                "parameters": S({"incident_id": {"type": "string"},
                                 "limit": {"type": "integer"}},
                                ["incident_id"]),
            },
            "get_authorized_assets": {
                "name": "get_authorized_assets",
                "description": "Authorized asset inventory for a zone",
                "parameters": S({"zone_id": {"type": "string"}}, ["zone_id"]),
            },
            "get_rf_activity": {
                "name": "get_rf_activity",
                "description": "Wi-Fi channel activity (NOT spectrum) for a zone+window",
                "parameters": S({"zone_id": {"type": "string"},
                                 "time_window_s": {"type": "integer"}},
                                ["zone_id"]),
            },
            "get_rover_status": {
                "name": "get_rover_status",
                "description": "Rover state/pose for a known device",
                "parameters": S({"device_id": {"type": "string"}}, ["device_id"]),
            },
            "request_rover_inspection": {
                "name": "request_rover_inspection",
                "description": "Queue a bounded inspect_zone mission on surveyed waypoint",
                "parameters": S({"zone_id": {"type": "string"},
                                 "waypoint_id": {"type": "string"}},
                                ["zone_id", "waypoint_id"]),
            },
            "request_sensor_rescan": {
                "name": "request_sensor_rescan",
                "description": "Ask a known puck to rescan now",
                "parameters": S({"device_id": {"type": "string"}}, ["device_id"]),
            },
            "get_evidence_metadata": {
                "name": "get_evidence_metadata",
                "description": "Metadata (sha256, source, trust tier) for evidence",
                "parameters": S({"evidence_id": {"type": "string"}}, ["evidence_id"]),
            },
            "append_agent_assessment": {
                "name": "append_agent_assessment",
                "description": "Append findings: assessment, evidence_ids, unknowns",
                "parameters": S({"incident_id": {"type": "string"},
                                 "assessment": {"type": "string"},
                                 "evidence_ids": {"type": "array"},
                                 "unknowns": {"type": "array"}},
                                ["incident_id", "assessment"]),
            },
            "propose_containment": {
                "name": "propose_containment",
                "description": "PROPOSE bounded containment for human approval — cannot approve/execute",
                "parameters": S({"incident_id": {"type": "string"},
                                 "action_type": {"type": "string"},
                                 "target_id": {"type": "string"},
                                 "reason": {"type": "string"}},
                                ["incident_id", "action_type", "target_id", "reason"]),
            },
            "post_incident_system_message": {
                "name": "post_incident_system_message",
                "description": "Post a system message to the incident timeline",
                "parameters": S({"incident_id": {"type": "string"},
                                 "message": {"type": "string"}},
                                ["incident_id", "message"]),
            },
        }

    # ---------------- dispatch ----------------
    def call(self, name: str, arguments: dict) -> ToolResult:
        """Validate scope + args, then invoke backend. All calls traced."""
        entry = {"tool": name, "args": dict(arguments)}
        try:
            if name not in self._specs:
                raise ToolDenied(f"tool '{name}' not in allowlist")
            self._check_scope(name, arguments)
            self._check_args(name, arguments)
            backend = self.backends.get(name)
            if backend is None:
                raise ToolDenied(f"no backend bound for '{name}'")
            data = backend(arguments)
            entry["ok"] = True
            return ToolResult(True, name, data=data)
        except ToolDenied as e:
            entry["ok"] = False
            entry["denied"] = True
            entry["error"] = e.reason
            return ToolResult(False, name, error=e.reason, denied=True)
        except Exception as e:  # backend failure — fail soft, keep trace
            entry["ok"] = False
            entry["error"] = f"backend_error: {e}"
            return ToolResult(False, name, error=f"backend_error: {e}")
        finally:
            self.calls.append(entry)

    def _check_scope(self, name: str, a: dict) -> None:
        ctx = self.ctx
        if a.get("incident_id") not in (None, "", ctx.incident_id):
            raise ToolDenied("incident_id outside agent scope")
        for arg_key, allowed in (("zone_id", ctx.allowed_zones),
                                 ("waypoint_id", ctx.allowed_waypoints),
                                 ("device_id", ctx.allowed_devices)):
            v = a.get(arg_key)
            if v and allowed and v not in allowed:
                raise ToolDenied(f"{arg_key} '{v}' outside incident scope")
        if name == "request_rover_inspection":
            if not ctx.allowed_waypoints:
                raise ToolDenied("no surveyed waypoints in scope")

    def _check_args(self, name: str, a: dict) -> None:
        spec = self._specs[name]["parameters"]
        _req(a, *spec.get("required", []))
        # reject unknown args (strict schemas)
        allowed = set(spec.get("properties", {}))
        extra = set(a) - allowed
        if extra:
            raise ToolDenied(f"unexpected args: {sorted(extra)}")
        # type sanity
        for k, v in a.items():
            t = spec["properties"].get(k, {}).get("type")
            if t == "string" and not isinstance(v, str):
                raise ToolDenied(f"arg {k} must be string")
            if t == "integer" and not isinstance(v, int):
                raise ToolDenied(f"arg {k} must be integer")
            if t == "array" and not isinstance(v, list):
                raise ToolDenied(f"arg {k} must be array")


def registry_from_backends(ctx: ToolContext, backends: dict) -> ToolRegistry:
    return ToolRegistry(ctx, backends)
