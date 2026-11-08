"""Scheduled posture assessment runner (#102 remainder).

Polls live node services (#101 vpi_service endpoints) or fixtures,
feeds NodeView-compatible snapshots into PostureEngine, emits findings.
Read-only: no remediation, no live scanning beyond the declared HTTP
endpoints, no Nemotron calls.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from .engine import NodeView, PostureEngine, Provider, Provenance


@dataclass
class HttpNodeView:
    """NodeView backed by a vpi_service HTTP endpoint."""
    base_url: str
    node_id: str
    zone_id: str = "rack-01"
    timeout_s: float = 2.0
    services: tuple = ()
    config: dict = None
    baseline: dict = None
    open_ports: tuple = ()
    patch_level: str = "unknown"
    credentials: tuple = ()

    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(
                self.base_url.rstrip("/") + path, timeout=self.timeout_s) as r:
            return json.loads(r.read())

    def refresh(self) -> None:
        cfg = self._get("/config")
        svcs = self._get("/services")
        self.config = cfg.get("config", {})
        self.baseline = dict(self.config)
        self.baseline["expected_patch_level"] = "2026-10"
        self.services = tuple(svcs.get("services", ()))
        # open_ports derived from declared services (no active scan —
        # read-only scope per issue)
        self.open_ports = tuple(
            {"port": s["port"], "proto": s.get("protocol", "tcp"),
             "service_name": s["name"]}
            for s in self.services if s.get("port"))


class HttpProvider:
    """Provider over live vpi_service endpoints."""

    def __init__(self, nodes: list[HttpNodeView],
                 provenance=Provenance.LIVE):
        self._nodes = nodes
        self._prov = provenance

    def nodes(self):
        return self._nodes

    def provenance(self):
        return self._prov


class AssessmentRunner:
    """Periodic assessment loop (manual tick() or run_forever)."""

    def __init__(self, provider: Provider, engine: Optional[PostureEngine] = None,
                 interval_s: float = 60.0,
                 on_findings: Optional[Callable[[list[dict]], None]] = None):
        self.provider = provider
        self.engine = engine or PostureEngine(provider)
        self.interval_s = interval_s
        self.on_findings = on_findings
        self.history: list[list[dict]] = []

    def assess_once(self) -> list[dict]:
        # refresh live views before assessing
        for n in self.provider.nodes():
            if hasattr(n, "refresh"):
                try:
                    n.refresh()
                except Exception:
                    # unreachable node -> empty view -> engine emits
                    # insufficient_evidence/unknown, never silent pass
                    n.services = ()
                    n.config = {}
                    n.baseline = {}
                    n.open_ports = ()
        findings = self.engine.assess()
        self.history.append(findings)
        if self.on_findings:
            self.on_findings(findings)
        return findings

    def run_forever(self, max_cycles: int = 0) -> None:
        cycles = 0
        while True:
            self.assess_once()
            cycles += 1
            if max_cycles and cycles >= max_cycles:
                return
            time.sleep(self.interval_s)


def runner_from_env(node_urls: dict[str, str],
                    provenance=Provenance.LIVE) -> AssessmentRunner:
    """Build runner from {node_id: base_url} map (e.g. compose service DNS)."""
    zones = {"vpi-compute-01": "rack-01", "vpi-network-01": "lab-b",
             "vpi-sensor-01": "rack-01", "vpi-mgmt-01": "bench-row"}
    views = [HttpNodeView(base_url=url, node_id=nid,
                          zone_id=zones.get(nid, "lab-floor"))
             for nid, url in node_urls.items()]
    return AssessmentRunner(HttpProvider(views, provenance))
