"""Flow-decision contract models — issue #105.

Virtual defense gateway: explicit allow/block/redirect decisions for
authorized simulated traffic. This module defines the CONTRACT only —
nothing here touches a real packet path. Enforcement is a separate
component (#106 lab proxy/firewall); every decision record is stamped
enforcement="simulated" so a policy outcome is never mistaken for a
verified enforcement.

Field set per issue #105: flow_id, src/dst node+service, decision
allow|block|redirect, reason, policy_id, TTL — plus repo-standard
schema_version, provenance (DEMO|REPLAY|LIVE per docs/04 + #95
contracts) and trace_id.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SCHEMA_VERSION = 1
ENGINE_VERSION = "defense-gateway/0.1.0"

MAX_ID_LEN = 128
MAX_SERVICE_LEN = 64
MAX_REASON_LEN = 512
MAX_TRACE_LEN = 128
DEFAULT_TTL_S = 60.0
MAX_TTL_S = 3600.0

# ASCII-only, bounded — mirrors services/gateway/src/validate.ts style.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class FlowValidationError(ValueError):
    """Raised when a flow tuple, endpoint, rule or policy violates the
    contract. Malformed input is rejected, never silently coerced."""


class Provenance(str, Enum):
    """docs/04 + #95 contracts vocabulary — simulated data must never
    be presented as LIVE."""
    DEMO = "DEMO"        # synthetic fixture / lab-generated
    REPLAY = "REPLAY"    # recorded capture
    LIVE = "LIVE"        # real device/service measurement


class FlowDecisionKind(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REDIRECT = "redirect"


class DefaultAction(str, Enum):
    """Policy choice for flows matching no rule — explicit, documented,
    tested (issue #105 acceptance)."""
    DENY = "deny"        # fail-closed: unmatched -> block
    MONITOR = "monitor"  # fail-open:  unmatched -> allow, flagged via rule_id=None


class EnforcementStatus(str, Enum):
    """Honesty label. This contract only ever emits SIMULATED; a real
    enforcement claim requires the #106+ verified path."""
    SIMULATED = "simulated"


def _require_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise FlowValidationError(f"{name} must be a non-empty string")
    if len(value) > MAX_ID_LEN:
        raise FlowValidationError(f"{name} exceeds {MAX_ID_LEN} chars")
    if not _ID_RE.match(value):
        raise FlowValidationError(
            f"{name} '{value}' has invalid characters (allowed: A-Za-z0-9_.-)")
    return value


def _require_service(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise FlowValidationError(f"{name} must be a non-empty string")
    if len(value) > MAX_SERVICE_LEN:
        raise FlowValidationError(f"{name} exceeds {MAX_SERVICE_LEN} chars")
    if not _SERVICE_RE.match(value):
        raise FlowValidationError(
            f"{name} '{value}' has invalid characters (allowed: a-z0-9_.-)")
    return value


def _require_reason(value: Any, name: str = "reason") -> str:
    if not isinstance(value, str):
        raise FlowValidationError(f"{name} must be a string")
    if len(value) > MAX_REASON_LEN:
        raise FlowValidationError(f"{name} exceeds {MAX_REASON_LEN} chars")
    return value


def _require_ttl(value: Any, name: str = "ttl_s") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FlowValidationError(f"{name} must be a number")
    ttl = float(value)
    if not (0 < ttl <= MAX_TTL_S):
        raise FlowValidationError(f"{name} must be in (0, {MAX_TTL_S}]")
    return ttl


@dataclass(frozen=True)
class FlowEndpoint:
    """One side of a flow: a virtual node plus the service it exposes
    or consumes (e.g. node_id='dc-pi-02', service='http')."""
    node_id: str
    service: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _require_id(self.node_id, "node_id"))
        object.__setattr__(self, "service", _require_service(self.service, "service"))

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "service": self.service}

    def __str__(self) -> str:
        return f"{self.node_id}/{self.service}"


@dataclass(frozen=True)
class FlowTuple:
    """The flow identity a decision is made about. `provenance` records
    where the flow metadata came from — a required field (matching the
    frozen SourceEnvelope contract), so simulated flows stay honestly
    labeled and callers must choose DEMO/REPLAY/LIVE explicitly."""
    flow_id: str
    src: FlowEndpoint
    dst: FlowEndpoint
    provenance: Provenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _require_id(self.flow_id, "flow_id"))
        if not isinstance(self.src, FlowEndpoint):
            raise FlowValidationError("src must be a FlowEndpoint")
        if not isinstance(self.dst, FlowEndpoint):
            raise FlowValidationError("dst must be a FlowEndpoint")
        try:
            prov = Provenance(self.provenance)
        except ValueError as e:
            raise FlowValidationError(f"invalid provenance: {e}") from e
        object.__setattr__(self, "provenance", prov)

    def validate(self) -> None:
        """Re-check invariants; cheap, called by the engine defensively."""
        _require_id(self.flow_id, "flow_id")
        if not isinstance(self.src, FlowEndpoint) or not isinstance(self.dst, FlowEndpoint):
            raise FlowValidationError("src/dst must be FlowEndpoint")

    def as_dict(self) -> dict:
        return {
            "flow_id": self.flow_id,
            "src": self.src.as_dict(),
            "dst": self.dst.as_dict(),
            "provenance": self.provenance.value,
        }


@dataclass(frozen=True)
class FlowMatch:
    """Rule match criteria. Every specified (non-None) field must equal
    the flow's corresponding field; None is a wildcard. An all-None
    match matches every flow — permitted (e.g. a documented catch-all
    rule) since rule order is explicit and first-match-wins."""
    src_node: str | None = None
    src_service: str | None = None
    dst_node: str | None = None
    dst_service: str | None = None

    def __post_init__(self) -> None:
        for name in ("src_node", "dst_node"):
            v = getattr(self, name)
            if v is not None:
                object.__setattr__(self, name, _require_id(v, name))
        for name in ("src_service", "dst_service"):
            v = getattr(self, name)
            if v is not None:
                object.__setattr__(self, name, _require_service(v, name))

    def matches(self, flow: FlowTuple) -> bool:
        checks = (
            (self.src_node, flow.src.node_id),
            (self.src_service, flow.src.service),
            (self.dst_node, flow.dst.node_id),
            (self.dst_service, flow.dst.service),
        )
        return all(spec is None or spec == actual for spec, actual in checks)

    def as_dict(self) -> dict:
        return {k: v for k, v in (
            ("src_node", self.src_node), ("src_service", self.src_service),
            ("dst_node", self.dst_node), ("dst_service", self.dst_service),
        ) if v is not None}


@dataclass(frozen=True)
class FlowRule:
    """One ordered policy rule. First matching rule in policy order
    wins — deterministic, documented, test-covered."""
    rule_id: str
    match: FlowMatch
    action: FlowDecisionKind
    redirect_to: FlowEndpoint | None = None
    reason: str = ""
    ttl_s: float | None = None  # None -> policy.default_ttl_s

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _require_id(self.rule_id, "rule_id"))
        if not isinstance(self.match, FlowMatch):
            raise FlowValidationError("match must be a FlowMatch")
        try:
            action = FlowDecisionKind(self.action)
        except ValueError as e:
            raise FlowValidationError(f"invalid action: {e}") from e
        object.__setattr__(self, "action", action)
        if self.redirect_to is not None and not isinstance(self.redirect_to, FlowEndpoint):
            raise FlowValidationError("redirect_to must be a FlowEndpoint or None")
        if action is FlowDecisionKind.REDIRECT and self.redirect_to is None:
            raise FlowValidationError("redirect rules require redirect_to")
        if action is not FlowDecisionKind.REDIRECT and self.redirect_to is not None:
            raise FlowValidationError("redirect_to only valid for redirect rules")
        object.__setattr__(self, "reason", _require_reason(self.reason))
        if self.ttl_s is not None:
            object.__setattr__(self, "ttl_s", _require_ttl(self.ttl_s))

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "match": self.match.as_dict(),
            "action": self.action.value,
            "redirect_to": self.redirect_to.as_dict() if self.redirect_to else None,
            "reason": self.reason,
            "ttl_s": self.ttl_s,
        }


@dataclass
class FlowPolicy:
    """Ordered rule list + explicit default for unmatched flows.
    `default_action` is a required, documented choice — there is no
    implicit fail-open."""
    policy_id: str
    version: int = 1
    rules: list[FlowRule] = field(default_factory=list)
    default_action: DefaultAction = DefaultAction.DENY
    default_ttl_s: float = DEFAULT_TTL_S

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _require_id(self.policy_id, "policy_id"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise FlowValidationError("version must be an int >= 1")
        try:
            default = DefaultAction(self.default_action)
        except ValueError as e:
            raise FlowValidationError(f"invalid default_action: {e}") from e
        object.__setattr__(self, "default_action", default)
        object.__setattr__(self, "default_ttl_s", _require_ttl(self.default_ttl_s, "default_ttl_s"))
        if not isinstance(self.rules, list) or not all(isinstance(r, FlowRule) for r in self.rules):
            raise FlowValidationError("rules must be a list of FlowRule")
        ids = [r.rule_id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise FlowValidationError("duplicate rule_id in policy")

    def as_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "rules": [r.as_dict() for r in self.rules],
            "default_action": self.default_action.value,
            "default_ttl_s": self.default_ttl_s,
        }


@dataclass(frozen=True)
class FlowDecision:
    """The policy outcome for one flow. This is a DECISION record —
    `enforcement` is always SIMULATED here; real enforcement evidence
    comes from the #106+ verified path, never from this object."""
    decision_id: str
    flow: FlowTuple
    decision: FlowDecisionKind
    reason: str
    policy_id: str
    policy_version: int
    rule_id: str | None
    redirect_to: FlowEndpoint | None
    ttl_s: float
    decided_at: str
    trace_id: str = ""
    provenance: Provenance = Provenance.DEMO
    enforcement: EnforcementStatus = EnforcementStatus.SIMULATED
    engine: str = ENGINE_VERSION
    schema_version: int = SCHEMA_VERSION

    @property
    def matched(self) -> bool:
        """False => produced by the default (unmatched) policy path."""
        return self.rule_id is not None

    def content_hash(self) -> str:
        """Deterministic sha256 over the contract-relevant fields —
        stable across re-evaluation of the same flow+policy, usable as
        a correlation key downstream (#106/#108)."""
        material = {
            "flow": self.flow.as_dict(),
            "decision": self.decision.value,
            "reason": self.reason,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "rule_id": self.rule_id,
            "redirect_to": self.redirect_to.as_dict() if self.redirect_to else None,
            "ttl_s": self.ttl_s,
            "provenance": self.provenance.value,
        }
        return hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def as_record(self) -> dict:
        """Canonical JSON-able contract record (schema_version=1)."""
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "flow": self.flow.as_dict(),
            "decision": self.decision.value,
            "reason": self.reason,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "rule_id": self.rule_id,
            "redirect_to": self.redirect_to.as_dict() if self.redirect_to else None,
            "ttl_s": self.ttl_s,
            "decided_at": self.decided_at,
            "trace_id": self.trace_id,
            "provenance": self.provenance.value,
            "enforcement": self.enforcement.value,
            "engine": self.engine,
            "content_hash": self.content_hash(),
        }


def utc_now_iso(ts: float | None = None) -> str:
    t = time.time() if ts is None else ts
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")
