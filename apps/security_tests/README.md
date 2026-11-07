# Threat-model automation + isolation attack evidence (issue #24)

Automated adversarial checks against every security boundary in
`docs/08-SECURITY-THREAT-MODEL.md`, emitting PASS/FAIL evidence
artifacts per docs/06 + docs/10.

## Six boundary checks

| ID | Boundary | What it attacks |
|---|---|---|
| B1 | network deny paths | machine/inactive/hostile principals obtaining sessions |
| B2 | telemetry forgery | bad HMAC, replayed event_id, stale seq on observation ingest |
| B3 | subscription enumeration | cross-incident/unknown-room/unknown-user subscriptions |
| B4 | expired sessions | time-expired + revoked tokens on every service |
| B5 | evidence upload | oversized, disallowed mime, magic-byte spoof, path traversal, invalid JSON |
| B6 | identity boundary | device/agent human-login, inactive/unknown users, forged tokens |

## Usage

```sh
cd apps/security_tests
PYTHONPATH=src python3 -m pytest tests/ -q          # harness self-tests
PYTHONPATH=src python3 -m threat_tests --out report  # emits report.json + report.md
```

`--mode live_endpoint` reserves the flag for real-deployment runs —
checks are injectable: same `CheckResult` contract against real
endpoints once deployed.

## Evidence artifacts

`report.json` — machine-readable: run_id (timestamp+git sha), mode,
per-check status + evidence payload. `report.md` — human table +
per-check JSON evidence blocks. Both designed to be committed as
incident/demo evidence; run_id ties PASS to a specific build.

## NOT done — simulated, not deployed

- Checks run against **in-memory service doubles** (`FakeIdP`,
  `FakeRelay`, `FakeSubscriptions`, `FakeEvidenceStore`) — they prove
  the *test logic* detects breaches (self-tests sabotage doubles and
  assert FAIL), NOT that real infrastructure resists attack.
- W01/W02 acceptance requires these same checks against the deployed
  control plane, IdP, SpacetimeDB subscriptions and evidence store —
  pending real Winstead deployment.
- No screenshots possible without running services; markdown report
  is the current evidence format.
