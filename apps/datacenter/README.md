# apps/datacenter — virtual Pi node model + simulator (#125)

Deterministic simulator for four virtual Raspberry Pi nodes in the
Meridian PHX-1 data center. No transport, no SpacetimeDB, no UI —
#100 wires publishing through the gateway later.

## Model

- `NodeProfile` — static identity: node_id, role
  (compute/network/sensor/management), services, addresses, config
  baseline (sha256 hash for drift checks).
- `SimNode` — runtime: health (ok/degraded/fault/stale), killed/hung
  flags, per-node seq, heartbeat tracking, drift map.
- `DataCenterSim` — seeded RNG, logical clock (1 tick = 1s),
  `tick()` returns contract-shaped observation dicts.

## Envelope

Emitted dicts match `docs/13-INTEGRATION-CONTRACTS.md` §1:
`schema_version=1, event_id, device_id, seq, observed_at, kind,
zone_id, data`. Kinds used: `device_health`, `temperature`.
`observed_at` is derived from the logical clock (deterministic), not
wall time.

## Failure injection

- `kill(node_id)` — immediate fault + fault observation
- `hung=True` — silent death; sim infers STALE after
  `stale_after_ticks` missed heartbeats
- `inject_drift(node_id, key, value)` — config drift → degraded

Kill/hang one node: others unaffected (isolation test proves it).

## Usage

```python
from datacenter import DataCenterSim
sim = DataCenterSim(seed=7)
for _ in range(60):
    obs = sim.tick()   # list of canonical observation dicts
sim.kill("vpi-sensor-01")
sim.inject_drift("vpi-compute-01", "ssh_password_auth", True)
```

## Tests

`PYTHONPATH=src python3 -m pytest tests` — 10 checks: determinism,
reset, envelope fields, seq monotonicity, node isolation, staleness,
drift, unique event IDs.
