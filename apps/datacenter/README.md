# apps/datacenter — virtual Pi node model + simulator (#125, #100)

Deterministic simulator for four virtual Raspberry Pi nodes in the
Meridian PHX-1 data center, plus controlled attack/benign scenarios and
a signed MQTT publisher into the SENTINEL HIVE gateway → SpacetimeDB.

## Model

- `NodeProfile` — static identity: node_id, role
  (compute/network/sensor/management), services, addresses, config
  baseline (sha256 hash for drift checks).
- `SimNode` — runtime: health (ok/degraded/fault/stale), killed/hung
  flags, per-node seq, heartbeat tracking, drift map, extra listeners,
  CPU override.
- `DataCenterSim` — seeded RNG, logical clock (1 tick = 1s),
  `tick()` returns contract-shaped observation dicts.

## Envelope

Emitted dicts match `docs/13-INTEGRATION-CONTRACTS.md` §1:
`schema_version=1, event_id, device_id, seq, observed_at, kind,
zone_id, data`. Kinds: `device_health`, `temperature`,
`resource_metric`, `service_inventory`, `network_flow`, `config_drift`.
`observed_at` is derived from the logical clock (deterministic), not
wall time. This is the SAME contract future physical Raspberry Pi
monitoring agents must emit — see docs/13 §5 for the `data` shapes.

## Failure injection & scenario primitives

- `kill(node_id)` / `revive(node_id)` — fault + recovery observations
- `hung=True` — silent death; sim infers STALE after
  `stale_after_ticks` missed heartbeats
- `inject_drift(node_id, key, value)` / `heal_drift(...)` — config drift
  → degraded + `config_drift` observations
- `inject_service(node_id, name, port)` / `heal_service(...)` —
  unexpected listener → `service_inventory` with `unexpected[]`
- `set_load(node_id, cpu_pct)` / `clear_load(...)` — sustained CPU for
  `resource_metric` reports
- `emit_flow(node_id, **facts)` — objective `network_flow` records

All injection observations are queued and delivered by the next
`tick()`/`drain()` — nothing is silently dropped. Kill/hang one node:
others unaffected (isolation test proves it).

## Scenarios (`datacenter.scenarios`)

`python -m datacenter.scenarios [--ticks N] [--scenario NAME] [--publish]`

Runs baseline, node_offline, unexpected_service, config_drift,
suspicious_traffic, benign_high_cpu. Writes per-scenario
`artifacts/<name>/observations.jsonl` plus a shared
`artifacts/ground_truth.json`. **Ground truth is evaluation-only** —
it is never merged into observations, never published, and never
visible to Nemotron; observations carry objective fields only.

## Publisher

`SimPublisher` signs each observation (HMAC-SHA256, same canonical form
as sensors/pucks + gateway `verifyDeviceSignature`) and publishes to
`sentinel/v1/<device_id>/telemetry` via MQTT env contract
(`MQTT_HOST/PORT/USERNAME/PASSWORD/CLIENT_ID`). Console fallback for
tests. Per-device secrets come from the `secrets` map or
`DC_HMAC_KEYS` JSON env (values used verbatim as UTF-8 — identical to
the gateway's `GATEWAY_DEVICE_HMAC_KEYS` key bytes) — must match
`GATEWAY_DEVICE_HMAC_KEYS` entries for signature enforcement.

Trust path: MQTT broker ACL (`device-datacenter-sim` may write only the
four `vpi-*/telemetry` topics) → gateway validate.ts (envelope +
signature) → `ingestObservation` (gateway_validated) → deterministic
correlation → deduplicated alerts/incidents.

## Usage

```python
from datacenter import DataCenterSim, SimPublisher
sim = DataCenterSim(seed=7)
pub = SimPublisher(sim=sim, secrets={...})   # or console transport
for _ in range(60):
    pub.tick()                               # sign + publish
sim.kill("vpi-sensor-01")
sim.inject_drift("vpi-compute-01", "ssh_password_auth", True)
```

## Tests

`PYTHONPATH=src python3 -m pytest tests` — envelope contract,
determinism/reset, seq monotonicity, node isolation, staleness, drift,
injection delivery, periodic self-reports, scenario correctness,
ground-truth separation, signing, posture-engine bridge.
