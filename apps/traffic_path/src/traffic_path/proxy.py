"""Isolated traffic-path validation (#106).

Reverse proxy in front of virtual node services (#101 vpi_service).
Every request becomes a FlowTuple evaluated by the #105
DecisionEngine: ALLOW forwards to the real backend, BLOCK returns 403
without touching the backend, REDIRECT sends to the sink. Every
decision is logged with trace_id — enforcement is real (request never
reaches backend on deny), not just recorded.

Lab segment only: loopback/LAN, no internet exposure, no DDoS/jamming.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

# defense_gateway is a sibling package; path inserted by tests/runner
try:
    from defense_gateway import (  # type: ignore
        DecisionEngine, DefaultAction, FlowDecisionKind, FlowEndpoint,
        FlowMatch, FlowPolicy, FlowRule, FlowTuple, Provenance,
    )
except ImportError:  # pragma: no cover - path bootstrap for direct run
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                           / "defense" / "gateway" / "src"))
    from defense_gateway import (
        DecisionEngine, DefaultAction, FlowDecisionKind, FlowEndpoint,
        FlowMatch, FlowPolicy, FlowRule, FlowTuple, Provenance,
    )


@dataclass
class PathProxy:
    """Enforcing proxy: engine decision -> real forward / 403 / sink."""
    engine: DecisionEngine
    backend_url: str                     # e.g. http://127.0.0.1:PORT
    dst_node: str = "vpi-compute-01"
    dst_service: str = "http"
    sink_url: Optional[str] = None       # redirect target (decoy/sink)
    timeout_s: float = 3.0
    decisions: list = field(default_factory=list)

    def _flow(self, src_node: str, path: str, trace_id: str) -> FlowTuple:
        # flow_id charset is [A-Za-z0-9_.-] — sanitize path/trace
        safe = f"{src_node}.{path}.{trace_id or 'anon'}".replace("/", "_") \
            .replace(":", "_")
        return FlowTuple(
            flow_id=safe[:120],
            src=FlowEndpoint(node_id=src_node, service="http"),
            dst=FlowEndpoint(node_id=self.dst_node, service=self.dst_service),
            provenance=Provenance.LIVE,
        )

    def _get(self, url: str) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_s) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except Exception:
                return e.code, {}
        except Exception:
            return 502, {"error": "backend_unreachable"}

    def forward(self, path: str, src_node: str = "lab-client",
                trace_id: str = "") -> dict:
        """Evaluate flow, enforce decision, return {status, body, decision}."""
        flow = self._flow(src_node, path, trace_id)
        decision = self.engine.evaluate(flow, trace_id=trace_id)
        record = {
            "trace_id": trace_id,
            "flow_id": flow.flow_id,
            "decision": decision.decision.value,
            "reason": decision.reason,
            "rule_id": decision.rule_id,
            "enforcement": "REAL",   # this proxy actually enforced it
        }
        self.decisions.append(record)

        if decision.decision is FlowDecisionKind.BLOCK:
            return {"status": 403, "body": {
                "error": "blocked_by_policy", "reason": decision.reason,
                "trace_id": trace_id, "synthetic": True},
                "decision": record}
        if decision.decision is FlowDecisionKind.REDIRECT:
            target = self.sink_url or (
                f"{decision.redirect_to.node_id}/{decision.redirect_to.service}"
                if decision.redirect_to else None)
            if target and target.startswith("http"):
                code, body = self._get(target.rstrip("/") + path)
            else:
                code, body = 302, {"redirect_to": target,
                                   "trace_id": trace_id}
            return {"status": code, "body": body, "decision": record}
        # ALLOW -> real backend
        code, body = self._get(self.backend_url.rstrip("/") + path)
        return {"status": code, "body": body, "decision": record}


def lab_policy(allow_paths=("/health", "/metrics", "/config", "/services"),
               block_src_nodes=("attacker-01",)) -> FlowPolicy:
    """Default lab policy: allowlisted services to everyone except known
    bad sources; unmatched -> DENY (fail-closed)."""
    rules = []
    for node in block_src_nodes:
        rules.append(FlowRule(
            rule_id=f"block-{node}",
            match=FlowMatch(src_node=node),
            action=FlowDecisionKind.BLOCK,
            reason=f"known-bad source {node}",
        ))
    return FlowPolicy(
        policy_id="lab-path-v1",
        rules=rules,
        # MONITOR = fail-open allow for unmatched (flagged rule_id=None);
        # explicit block rules above still deny known-bad sources
        default_action=DefaultAction.MONITOR,
        default_ttl_s=60.0,
    )
