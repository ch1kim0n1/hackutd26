# apps/posture — security posture assessment engine (#126)

Read-only checks over a node/provider interface. Produces structured
findings before any attacker event. Fixture-driven until #101 nodes
exist.

## Checks

| check_id | Detects |
|---|---|
| `open_port_unexpected` | listeners not in service baseline |
| `default_credential` | weak/default credential markers |
| `missing_patch` | patch level behind expected |
| `baseline_drift_new` / `_known` | live config vs baseline (new vs accepted) |
| `insufficient_evidence` | node with no assessable surface → `unknown` |

## Finding schema

`{check_id, node_ref, severity, confidence, provenance,
evidence_refs, detail}` — severity: info..critical; confidence:
unknown/suspected/confirmed. `unknown` patch level downgrades to
`unknown` confidence, never confirmed. Insufficient evidence yields
`unknown`, never silence.

## Provider interface

`Provider.nodes() -> list[NodeView]`, `provenance() -> Provenance`.
`NodeView` mirrors the #125 node model shape but is its own schema —
swap `FixtureProvider` for a live provider when #101 lands. Import-only
boundary with `apps/scope_matrix` (no modification).

## Usage

```python
from posture import PostureEngine, seed_weak_fixture
findings = PostureEngine(seed_weak_fixture()).assess()
# sorted: severity desc, node, check — deterministic
```

## Tests

`PYTHONPATH=src python3 -m pytest tests` — 7 checks: seeded weakness
discovery, schema fields, unknown preservation, new-vs-known drift,
determinism, insufficient-evidence, clean-node silence.
