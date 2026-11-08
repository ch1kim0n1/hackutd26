# 15 — Developer Runbook

How to bring up the Phantom Patrol software stack locally, verify each tier,
and run the foundation end-to-end test. All credentials are runtime-only:
they live in gitignored files under `deploy/` and are never committed.

## Stack overview

| Tier | Component | Default address |
|---|---|---|
| Time-series DB | SpacetimeDB | `ws://127.0.0.1:3000` (HTTP ping `/v1/ping`), database `sentinel-hive` |
| Message bus | Mosquitto MQTT | `tcp://127.0.0.1:1883`, topic prefix `sentinel/v1` |
| Edge gateway | `services/gateway` | health `http://127.0.0.1:8081/healthz` |
| Python API | `apps/api` (FastAPI) | `http://127.0.0.1:8000` |
| Lab executor | `sh-lab-executor` container | policy-gated defensive actions |

Data flow: device telemetry → MQTT → gateway (HMAC verify, normalize) →
`ingestObservation` reducer → `observationFeed`; incidents via role-scoped
reducers → `incidentFeed`. All dashboard reads are authenticated SpacetimeDB
subscriptions; containment stays approval-gated and verified.

## Prerequisites

- Docker (for `sh-spacetimedb`, `sh-mosquitto`, `sh-lab-executor`)
- Node 20+ (`services/gateway`, `services/mission-shim`)
- Python 3.11+ with `fastapi`/`uvicorn` (`apps/api`)

## Bring-up

```sh
# 1. Secrets + env (idempotent; never overwrites set values)
deploy/scripts/bootstrap.sh        # writes deploy/secrets/, deploy/env/*.env

# 2. Containers
docker compose -f deploy/compose.yaml up -d

# 3. SpacetimeDB module publish (first run only, or after schema changes)
cd spacetimedb && spacetimedb publish --server local sentinel-hive

# 4. Gateway
cd services/gateway && npm install
set -a; . ../../deploy/env/gateway.env; set +a
npm run dev                        # or: npm start

# 5. API facade (optional for the e2e; enables the api.facade leg)
cd apps/api && PYTHONPATH=src python3 -m uvicorn sentinel_api.app:app --port 8000
```

## Health checks

```sh
curl -s http://127.0.0.1:3000/v1/ping                       # SpacetimeDB
curl -s http://127.0.0.1:8081/healthz                       # gateway (mqtt/std/executor links)
curl -s http://127.0.0.1:8000/healthz                       # API (+ agent_provider mode)
```

`/healthz` on the gateway reports `stats.ingested/rejected/dispatched` and
`lastError` — check it first when telemetry seems dropped (common cause:
`stale or replayed seq`, i.e. device sequence lower than persisted `lastSeq`).

## Foundation end-to-end test

```sh
cd services/gateway
npx tsx scripts/e2e-foundation.ts
```

Legs: SpacetimeDB ping → secrets present → gateway health → authenticated SDK
connect + view subscriptions → observation persistence → incident create/read →
read-after-refresh (second connection, exactly-one-row) → API facade
(incident + investigation smoke, skipped with guidance if API is down).

Evidence is written to `deploy/evidence/e2e-<timestamp>/result.json`
(gitignored). Credentials are read from `deploy/secrets/identities.json` and
`deploy/env/*.env` at runtime and never printed or persisted.

Observation leg note: if `deploy/env/mqtt.env` has no device password, the
script exercises `ingestObservation` directly with the gateway identity
(labelled `observation.ingest-reducer`) — same reducer the gateway calls,
proving persistence + view visibility but not the MQTT transport. Provision
device credentials via `bootstrap.sh` for the full `observation.mqtt-gateway`
leg.

Env overrides: `SPACETIMEDB_URI`, `SPACETIMEDB_DATABASE`,
`E2E_GATEWAY_HEALTH`, `E2E_API_BASE`, `E2E_GATEWAY_ENV`.

## Simulated vs live — read this before demoing

- **LIVE**: SpacetimeDB persistence, MQTT transport, gateway normalization,
  incident feeds, API facade, policy/approval gating — all real local services.
- **DEMO/simulated**: lab executor containment actions are simulated inside
  the authorized lab; they are NOT real network enforcement. Device telemetry
  in demos may be synthetic. The rover runs in software simulation only.
- **Nemotron**: `agent_provider.mode` in `/healthz` reports `live` vs `fake`.
  Live requires `NEMOTRON_MODEL_ID`, `NEMOTRON_ENDPOINT`, and an API key env
  (`NEMOTRON_API_KEY`/`NVIDIA_API_KEY`); otherwise the deterministic fake
  provider is used. Nemotron never runs onboard the rover and has no direct
  actuator/shell/firewall access.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `stale or replayed seq` in gateway health | Device seq ≤ persisted `lastSeq`; restart device seq or use a fresh `device_id` |
| Empty feeds despite subscribed views | Views only populate after subscription `onApplied`; the e2e handles this — custom clients must subscribe explicitly |
| MQTT publish denied | ACL requires `device-<id>` username publishing only `sentinel/v1/<id>/telemetry`; gateway account is subscribe-only for telemetry |
| `api.facade` SKIP/FAIL | API not running, or login user lacks role — use seeded `commander` |
| SpacetimeDB ping fails | Container down or module not published — `docker compose up -d`, then `spacetimedb publish` |
