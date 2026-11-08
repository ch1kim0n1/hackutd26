import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datacenter import (
    DataCenterSim, HealthState, PI_PROFILES, SCHEMA_VERSION,
    canonical_observation, tick_to_iso,
)
from datacenter.nodes import SimNode

ENVELOPE_KEYS = {"schema_version", "event_id", "device_id", "seq",
                 "observed_at", "kind", "zone_id", "data"}


def run_ticks(sim, n):
    out = []
    for _ in range(n):
        out.extend(sim.tick())
    return out


def test_four_profiles():
    assert len(PI_PROFILES) == 4
    roles = {p.role.value for p in PI_PROFILES}
    assert roles == {"compute", "network", "sensor", "management"}
    for p in PI_PROFILES:
        assert p.node_id and p.hostname and p.zone_id
        assert p.services and p.addresses
        assert len(p.baseline_hash) == 16


def test_determinism_and_reset():
    a = DataCenterSim(seed=42)
    b = DataCenterSim(seed=42)
    run_ticks(a, 30)
    run_ticks(b, 30)
    assert a.drain() == b.drain()          # identical observation streams
    a.reset()
    assert a.tick_count == 0 and all(
        n.seq == 0 and n.health == HealthState.OK for n in a.nodes.values())
    run_ticks(a, 30)
    b2 = DataCenterSim(seed=42)
    run_ticks(b2, 30)
    assert a.drain() == b2.drain()         # reset reproduces exactly


def test_different_seed_diverges():
    a = DataCenterSim(seed=1)
    b = DataCenterSim(seed=2)
    run_ticks(a, 200)
    run_ticks(b, 200)
    # temperature jitter is seeded; streams should differ somewhere
    assert a.drain() != b.drain()


KNOWN_KINDS = {"device_health", "temperature", "resource_metric",
               "service_inventory", "network_flow", "config_drift"}


def test_envelope_contract_fields():
    sim = DataCenterSim()
    obs = run_ticks(sim, 40)
    assert obs, "expected heartbeats within 10 ticks"
    for o in obs:
        assert set(o.keys()) == ENVELOPE_KEYS
        assert o["schema_version"] == SCHEMA_VERSION == 1
        assert o["event_id"].startswith("evt-")
        assert o["device_id"] in sim.nodes
        assert isinstance(o["seq"], int) and o["seq"] > 0
        assert o["kind"] in KNOWN_KINDS
        assert o["zone_id"]
        assert isinstance(o["data"], dict)


def test_seq_monotonic_per_node():
    sim = DataCenterSim()
    run_ticks(sim, 60)
    by_node = {}
    for o in sim.drain():
        by_node.setdefault(o["device_id"], []).append(o["seq"])
    for seqs in by_node.values():
        assert seqs == sorted(seqs)
        assert len(seqs) == len(set(seqs))


def test_node_isolation_kill():
    sim = DataCenterSim()
    sim.kill("vpi-sensor-01")
    before = {k: n.health for k, n in sim.nodes.items()}
    assert before["vpi-sensor-01"] == HealthState.FAULT
    # others unaffected
    for k, n in sim.nodes.items():
        if k != "vpi-sensor-01":
            assert n.health != HealthState.FAULT
    # killed node emits nothing after kill (only the kill event)
    obs = run_ticks(sim, 30)
    sensor_obs = [o for o in obs if o["device_id"] == "vpi-sensor-01"]
    assert all(o["data"].get("note") != "heartbeat" for o in sensor_obs)
    others = {o["device_id"] for o in obs if o["data"].get("note") == "heartbeat"}
    assert "vpi-compute-01" in others


def test_staleness_detected():
    sim = DataCenterSim()
    sim.kill("vpi-network-01")
    run_ticks(sim, 20)
    n = sim.nodes["vpi-network-01"]
    assert n.killed and n.health == HealthState.FAULT  # killed stays fault
    # hung node = silent death: no heartbeat, sim infers STALE
    sim3 = DataCenterSim()
    silent = sim3.nodes["vpi-mgmt-01"]
    silent.hung = True
    run_ticks(sim3, 20)
    assert silent.health == HealthState.STALE
    # stale observation emitted exactly once
    stale_obs = [o for o in sim3.drain()
                 if o["device_id"] == "vpi-mgmt-01"
                 and o["data"].get("status") == "stale"]
    assert len(stale_obs) == 1


def test_drift_marks_degraded():
    sim = DataCenterSim()
    sim.inject_drift("vpi-compute-01", "ssh_password_auth", True)
    obs = run_ticks(sim, 10)
    heartbeats = [o for o in obs
                  if o["device_id"] == "vpi-compute-01"
                  and o["data"].get("note") == "heartbeat"]
    assert heartbeats and heartbeats[-1]["data"]["status"] == "degraded"


def test_tick_to_iso_deterministic():
    assert tick_to_iso(0) == "2026-11-07T18:00:00.000Z"
    assert tick_to_iso(1) == "2026-11-07T18:00:01.000Z"
    assert tick_to_iso(1500) == "2026-11-07T18:25:00.000Z"


def test_injection_observations_delivered():
    """kill/inject_drift/revive queue observations that tick() must return —
    regression: _emit results used to be discarded silently."""
    sim = DataCenterSim()
    run_ticks(sim, 5)
    sim.kill("vpi-compute-01")
    sim.inject_drift("vpi-network-01", "lldp_tx", False)
    sim.revive("vpi-mgmt-01")
    obs = run_ticks(sim, 2)
    fault = [o for o in obs if o["device_id"] == "vpi-compute-01"
             and o["data"].get("status") == "fault"]
    assert fault, "kill() fault observation must reach the stream"
    drift = [o for o in obs if o["kind"] == "config_drift"
             and o["device_id"] == "vpi-network-01"]
    assert drift and drift[0]["data"]["key"] == "lldp_tx"
    rec = [o for o in obs if o["device_id"] == "vpi-mgmt-01"
           and o["data"].get("recovered") is True]
    assert rec, "revive() recovery observation must reach the stream"


def test_periodic_self_reports():
    sim = DataCenterSim()
    obs = run_ticks(sim, 35)
    kinds = {o["kind"] for o in obs}
    assert "resource_metric" in kinds       # every 10 ticks
    assert "service_inventory" in kinds     # every 30 ticks
    inv = [o for o in obs if o["kind"] == "service_inventory"]
    assert all(o["data"]["unexpected"] == [] for o in inv)
    rm = [o for o in obs if o["kind"] == "resource_metric"]
    assert all(0 <= o["data"]["cpu_pct"] <= 100 for o in rm)


def test_service_injection_and_heal():
    sim = DataCenterSim()
    run_ticks(sim, 3)
    sim.inject_service("vpi-compute-01", "minerd", 3333)
    obs = run_ticks(sim, 2)
    inv = [o for o in obs if o["kind"] == "service_inventory"
           and o["device_id"] == "vpi-compute-01"]
    assert inv and inv[0]["data"]["unexpected"] == [
        {"name": "minerd", "port": 3333, "proto": "tcp"}]
    sim.heal_service("vpi-compute-01", 3333)
    obs = run_ticks(sim, 2)
    inv = [o for o in obs if o["kind"] == "service_inventory"
           and o["device_id"] == "vpi-compute-01"]
    assert inv[-1]["data"]["unexpected"] == []


def test_emit_flow_and_load_override():
    sim = DataCenterSim()
    run_ticks(sim, 3)
    flow = sim.emit_flow("vpi-sensor-01", src="198.51.100.1",
                         dst="192.0.2.103", dst_port=4444,
                         packets=10, bytes=1000, direction="ingress")
    assert flow["kind"] == "network_flow"
    assert flow["data"]["dst_port"] == 4444
    sim.set_load("vpi-compute-01", 96.0)
    obs = run_ticks(sim, 10)               # crosses metric interval
    rm = [o for o in obs if o["kind"] == "resource_metric"
          and o["device_id"] == "vpi-compute-01"]
    assert rm and rm[-1]["data"]["cpu_pct"] == 96.0
    sim.clear_load("vpi-compute-01")


def test_observation_event_ids_unique():
    sim = DataCenterSim()
    run_ticks(sim, 40)
    ids = [o["event_id"] for o in sim.drain()]
    assert len(ids) == len(set(ids))
