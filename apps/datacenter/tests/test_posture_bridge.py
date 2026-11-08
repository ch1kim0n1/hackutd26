"""Posture engine over live simulator state (#126 x #125 bridge).

Builds posture NodeViews from DataCenterSim nodes — the same snapshots a
physical Pi monitoring agent would report — and verifies drift/fault
scenarios surface as findings while clean nodes stay silent.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # apps/
for rel in ("datacenter/src", "posture/src"):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from datacenter import DataCenterSim  # noqa: E402
from posture.engine import (  # noqa: E402
    FixtureNode, PostureEngine, Provenance,
)


def node_view(sim, node_id) -> FixtureNode:
    """SimNode -> posture NodeView (duck-typed FixtureNode)."""
    n = sim.nodes[node_id]
    p = n.profile
    live = dict(p.config_baseline)
    live.update(n.drift)
    baseline = dict(p.config_baseline)
    baseline["expected_patch_level"] = "2026-10"
    open_ports = tuple(
        {"port": s.port, "proto": s.protocol, "service_name": s.name}
        for s in p.services if s.port
    ) + tuple(
        {"port": l["port"], "proto": l["proto"],
         "service_name": l["name"]}
        for l in n.extra_listeners
    )
    return FixtureNode(
        node_id=node_id,
        zone_id=p.zone_id,
        services=tuple(
            {"name": s.name, "port": s.port, "protocol": s.protocol,
             "version": s.version} for s in p.services),
        config=live,
        baseline=baseline,
        open_ports=open_ports,
        patch_level="2026-10",
        credentials=(),
    )


class SimProvider:
    def __init__(self, sim, node_ids):
        self._sim = sim
        self._ids = node_ids

    def nodes(self):
        return [node_view(self._sim, n) for n in self._ids]

    def provenance(self):
        return Provenance.DEMO


def assess(sim, node_ids=None):
    ids = node_ids or list(sim.nodes)
    return PostureEngine(SimProvider(sim, ids)).assess()


def test_clean_sim_produces_no_drift_findings():
    sim = DataCenterSim(seed=1)
    for _ in range(35):
        sim.tick()
    findings = assess(sim)
    drift = [f for f in findings if f["check_id"].startswith("baseline_drift")]
    assert drift == [], f"unexpected drift findings: {drift}"
    ports = [f for f in findings if f["check_id"] == "open_port_unexpected"]
    assert ports == []


def test_injected_drift_and_service_surface_as_findings():
    sim = DataCenterSim(seed=2)
    for _ in range(5):
        sim.tick()
    sim.inject_drift("vpi-compute-01", "ssh_password_auth", True)
    sim.inject_service("vpi-compute-01", "minerd", 3333)
    findings = assess(sim, ["vpi-compute-01"])
    drift = [f for f in findings
             if f["check_id"] == "baseline_drift_new"
             and f["detail"]["key"] == "ssh_password_auth"]
    assert drift and drift[0]["detail"]["live"] is True
    ports = [f for f in findings if f["check_id"] == "open_port_unexpected"]
    assert ports and any(f["detail"]["port"] == 3333 for f in ports)


def test_healed_state_returns_clean():
    sim = DataCenterSim(seed=3)
    for _ in range(5):
        sim.tick()
    sim.inject_drift("vpi-mgmt-01", "ssh_password_auth", True)
    sim.inject_service("vpi-mgmt-01", "minerd", 3333)
    sim.heal_drift("vpi-mgmt-01", "ssh_password_auth")
    sim.heal_service("vpi-mgmt-01", 3333)
    findings = assess(sim, ["vpi-mgmt-01"])
    assert not [f for f in findings
                if f["check_id"].startswith("baseline_drift")
                or f["check_id"] == "open_port_unexpected"]
