"""Deception routing + evidence integration (#108).

Wraps the #105 DecisionEngine with an enforcing router: suspicious flows
matched by REDIRECT rules are sent to the #107 decoy service instead of
the real backend. Every routed flow produces an evidence record with
trace_id, decision_id, and decoy hit details — consumable by
incident_records and the #110 regression suite.

Fail-closed: decoy unreachable -> DENY evidence, real backend never
contacted for a redirected flow. Provenance flows through from the
FlowTuple; enforcement label stays SIMULATED (routing is real HTTP but
the *policy decision* was simulated-class until a live switch proves it).
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Callable

from defense_gateway.engine import DecisionEngine
from defense_gateway.models import (
    DefaultAction,
    FlowDecisionKind,
    FlowEndpoint,
    FlowMatch,
    FlowPolicy,
    FlowRule,
    FlowTuple,
    Provenance,
)

DECOY_NODE = "decoy-01"


@dataclass
class RouteResult:
    decision_id: str
    action: str            # allow | block | redirect
    status: int            # HTTP-ish status: 200/403/502
    body: bytes
    trace_id: str
    evidence: dict


class DeceptionRouter:
    """Policy-gated router: real backends + decoy sink."""

    def __init__(self, engine: DecisionEngine, *,
                 backends: dict[str, str],          # node_id -> base URL
                 decoy_url: str | None = None,
                 timeout_s: float = 5.0,
                 evidence_sink: Callable[[dict], None] | None = None):
        self.engine = engine
        self.backends = backends
        self.decoy_url = decoy_url
        self.timeout = timeout_s
        self.evidence_sink = evidence_sink or (lambda e: None)
        self.history: list[RouteResult] = []

    # ---------------- routing ----------------

    def route(self, flow: FlowTuple, path: str = "/",
              method: str = "GET", body: bytes = b"",
              trace_id: str = "") -> RouteResult:
        if not trace_id:
            import uuid
            trace_id = f"rt-{uuid.uuid4().hex[:12]}"
        decision = self.engine.evaluate(flow, trace_id=trace_id)
        trace = decision.trace_id

        if decision.decision is FlowDecisionKind.BLOCK:
            return self._finish(flow, decision, 403,
                                b'{"error":"blocked"}', trace,
                                routed_to=None)

        if decision.decision is FlowDecisionKind.REDIRECT:
            target = decision.redirect_to.node_id if decision.redirect_to else None
            if target == DECOY_NODE and self.decoy_url:
                return self._proxy(flow, decision, self.decoy_url,
                                   path, method, body, trace)
            # redirect to non-decoy or decoy not configured -> fail closed
            return self._finish(flow, decision, 403,
                                b'{"error":"redirect_unavailable"}', trace,
                                routed_to=target)

        # ALLOW -> real backend for dst node
        dst = flow.dst.node_id
        base = self.backends.get(dst)
        if base is None:
            return self._finish(flow, decision, 502,
                                b'{"error":"no_backend"}', trace,
                                routed_to=dst)
        return self._proxy(flow, decision, base, path, method, body, trace)

    # ---------------- internals ----------------

    def _proxy(self, flow, decision, base: str, path: str,
               method: str, body: bytes, trace: str) -> RouteResult:
        url = base.rstrip("/") + path
        req = urllib.request.Request(url, data=body or None, method=method)
        req.add_header("X-Sentinel-Trace", trace)
        req.add_header("X-Sentinel-Decision", decision.decision_id)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out, status = r.read(), r.status
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # redirected-to-decoy unreachable -> fail closed, no fallback
            evidence = self._evidence(flow, decision, "backend_error",
                                      str(e)[:120], trace)
            return self._finish(flow, decision, 502,
                                json.dumps({"error": "upstream",
                                            "trace_id": trace}).encode(),
                                trace, routed_to=base, evidence=evidence)

        hit = self._decoy_hit(out) if base == self.decoy_url else None
        evidence = self._evidence(flow, decision,
                                  "decoy_hit" if hit else "routed",
                                  "", trace, decoy=hit)
        return self._finish(flow, decision, status, out, trace,
                            routed_to=base, evidence=evidence)

    def _decoy_hit(self, body: bytes) -> dict | None:
        if not self.decoy_url:
            return None
        try:
            j = json.loads(body)
        except Exception:
            return None
        if j.get("synthetic") is True or j.get("device_id") == DECOY_NODE:
            return {"decoy_trace": j.get("trace_id"),
                    "synthetic": True,
                    "payload_sha256": hashlib.sha256(body).hexdigest()[:16]}
        return None

    def _evidence(self, flow, decision, outcome: str, detail: str,
                  trace: str, decoy: dict | None = None) -> dict:
        ev = {
            "schema": "deception-evidence/1",
            "trace_id": trace,
            "decision_id": decision.decision_id,
            "flow_id": flow.flow_id,
            "rule_id": decision.rule_id,
            "action": decision.decision.value,
            "outcome": outcome,
            "src": flow.src.as_dict(),
            "dst": flow.dst.as_dict(),
            "redirect_to": (decision.redirect_to.as_dict()
                            if decision.redirect_to else None),
            "provenance": flow.provenance.value,
            "enforcement": decision.enforcement.value,
            "at": time.time(),
            "detail": detail,
        }
        if decoy:
            ev["decoy"] = decoy
        self.evidence_sink(ev)
        return ev

    def _finish(self, flow, decision, status: int, body: bytes,
                trace: str, *, routed_to, evidence: dict | None = None):
        ev = evidence or self._evidence(flow, decision,
                                        "blocked" if status == 403 else "routed",
                                        "", trace)
        res = RouteResult(
            decision_id=decision.decision_id,
            action=decision.decision.value,
            status=status, body=body, trace_id=trace, evidence=ev)
        self.history.append(res)
        return res


def deception_policy(*, decoy_service: str = "http",
                     redirect_src_nodes: tuple[str, ...] = (),
                     redirect_dst_nodes: tuple[str, ...] = (),
                     block_src_nodes: tuple[str, ...] = (),
                     default: DefaultAction = DefaultAction.DENY) -> FlowPolicy:
    """Standard deception policy: block known-bad sources, redirect
    flagged sources to the decoy, explicit default."""
    rules = []
    for n in block_src_nodes:
        rules.append(FlowRule(
            rule_id=f"block-{n}",
            match=FlowMatch(src_node=n),
            action=FlowDecisionKind.BLOCK,
            reason="known-bad source"))
    for n in redirect_src_nodes:
        rules.append(FlowRule(
            rule_id=f"decoy-{n}",
            match=FlowMatch(src_node=n),
            action=FlowDecisionKind.REDIRECT,
            redirect_to=FlowEndpoint(node_id=DECOY_NODE,
                                     service=decoy_service),
            reason="suspicious source -> decoy"))
    for n in redirect_dst_nodes:
        rules.append(FlowRule(
            rule_id=f"decoy-dst-{n}",
            match=FlowMatch(dst_node=n),
            action=FlowDecisionKind.REDIRECT,
            redirect_to=FlowEndpoint(node_id=DECOY_NODE,
                                     service=decoy_service),
            reason="sensitive dst -> decoy"))
    return FlowPolicy(policy_id="deception-v1", rules=rules,
                      default_action=default, default_ttl_s=60.0)


def flow(flow_id: str, src_node: str, dst_node: str,
         *, src_service: str = "http", dst_service: str = "http",
         provenance: Provenance = Provenance.DEMO) -> FlowTuple:
    from defense_gateway.models import FlowEndpoint
    safe = "".join(c if c.isalnum() or c in "_.-" else "_"
                   for c in flow_id)[:120]
    return FlowTuple(
        flow_id=safe or "flow",
        src=FlowEndpoint(node_id=src_node, service=src_service),
        dst=FlowEndpoint(node_id=dst_node, service=dst_service),
        provenance=provenance)
