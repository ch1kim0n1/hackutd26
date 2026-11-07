# SENTINEL HIVE — constrained lab gateway (issue #17)

The single bridge between the untrusted office lab and the Winstead command
plane (docs/01 trust zones, docs/06 R-rules, docs/08 MQTT threat model).

```
lab device --MQTT QoS1--> gateway --ingestObservation--> SpacetimeDB
SpacetimeDB pendingMissions --> MQTT command --> rover/device
SpacetimeDB executorOutbox --> webhook --> recordExecutorOutcome
```

## What it does

- **Telemetry ingest.** Subscribes `<TOPIC_PREFIX>/+/telemetry`, validates the
  canonical envelope (`docs/04`): `schema_version == 1`, required bounded
  strings, known `kind`, integer `seq`, ISO `observed_at`, `data` object
  <= 8 KiB, packet <= 16 KiB. The **device identity comes from the MQTT
  topic** (`<prefix>/<device_id>/telemetry`) — a payload `device_id` that
  disagrees is rejected as forgery. Valid events are forwarded to
  `ingestObservation` as `trust_tier = gateway_validated`; the reducer
  enforces per-device seq replay protection, event-id dedupe and freshness.
- **Device-shape normalization.** Payloads that fail strict envelope
  validation are retried as device-native shapes. Rover mission-runtime
  events (`robotics/rover`: `mission_id`/`command_id`/`state`/`pose`, no
  `event_id`/`seq`/`kind`) are normalized to `kind=mission_status` with a
  deterministic `event_id` (`<device>:<mission>:<command>:<event>:<ts>`)
  and a gateway-assigned per-device monotonic `seq` persisted in
  `GATEWAY_STATE_FILE`, preserving replay protection and dedupe. See
  `test/validate.test.ts` (12 checks, no broker needed).
- **Mission downlink.** Watches the role-scoped `pending_missions` view and
  publishes each approved mission's canonical `commandJson` to
  `<prefix>/<device_id>/command`, then calls `markMissionDispatched`.
  Dispatched mission IDs are persisted in `GATEWAY_STATE_FILE` *before* the
  DB marker so a crash between publish and mark reconciles without
  duplicate commands on restart (rovers also dedupe on `mission_id`).
- **Action outbox worker.** Uses a *second* SpacetimeDB identity with the
  `executor` role (least privilege): watches `executor_outbox`, atomically
  `claimOutbox`, executes the approved payload (POST to
  `EXECUTOR_WEBHOOK_URL`, or a simulated lab ack when unset), then
  `recordExecutorOutcome`. `claimed` rows are finished after restart;
  completed outbox IDs are persisted to skip re-reporting.
- **Health.** `GET /healthz` -> `{ok, mqttConnected, stdConnected,
  executorConnected, stats}`; 503 until MQTT + SpacetimeDB are up.

## Configuration (env only — no secrets in repo)

| Var | Required | Purpose |
|-----|----------|---------|
| `SPACETIMEDB_URI` | no (default `ws://127.0.0.1:3000`) | SpacetimeDB WS endpoint |
| `SPACETIMEDB_DATABASE` | yes | e.g. `sentinel-hive` |
| `SPACETIMEDB_TOKEN` | yes | identity token for the `gateway` role |
| `EXECUTOR_SPACETIMEDB_TOKEN` | no | identity token for the `executor` role (outbox worker) |
| `MQTT_URL` | yes | e.g. `tcp://mosquitto:1883` |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | broker-dependent | broker credentials |
| `MQTT_TOPIC_PREFIX` | no (default `sentinel/v1`) | topic root |
| `EXECUTOR_WEBHOOK_URL` / `_TOKEN` | no | lab action executor endpoint |
| `GATEWAY_HEALTH_PORT` | no (default 8081) | health port |
| `GATEWAY_STATE_FILE` | no (default `./gateway-state.json`) | restart-reconcile state |

## Per-device MQTT ACLs (broker side)

The broker — not this service — enforces device isolation
(docs/08 threat 6). Pattern for mosquitto `aclfile`:

```
# gateway service: subscribe telemetry + commands topics it serves
user sentinel-gateway
pattern read sentinel/v1/+/telemetry
pattern write sentinel/v1/+/command

# each puck/rover: publish own telemetry, subscribe own command topic only
user device-puck-a-01
topic write sentinel/v1/puck-a-01/telemetry
pattern read sentinel/v1/puck-a-01/command
```

Devices authenticate with per-device credentials (or mTLS client certs in
the lab deployment); the gateway never accepts admin/command topics from
devices and never publishes telemetry upstream.

## Reconnect / failure behavior

- MQTT client auto-reconnects (2 s); subscriptions re-established on
  `connect`. QoS 1 on ingest publishes limits loss; SpacetimeDB dedupe
  (`event_id`, `seq`) makes redelivery safe.
- SpacetimeDB SDK `withAutomaticReconnect` replays subscriptions; views are
  server-authoritative so no local state is lost.
- Reducer `SenderError`s (stale seq, forged id, oversize) reject the MQTT
  message path only — counted in `stats.rejected`, never crash the worker.
- Outbox/mission reconciliation is DB-state-driven; the JSON state file is
  a crash-safety cache, safe to delete (worst case: one idempotent
  republish).

## Test

```sh
cd services/gateway
npm install
npm run generate      # client bindings -> bindings/ (gitignored)
npm run build         # tsc --noEmit
# requires local SpacetimeDB + seeded lab identities (deploy/seeds)
GATEWAY_TEST_TOKENS='{"gateway":"...","executor":"...","commander":"...","responder":"..."}' \
  npx tsx test/gateway.test.ts
```

The test boots an in-process aedes broker, launches the gateway, and
asserts 15 behaviors: health, ingest + `gateway_validated` trust tier,
event-id dedupe, forged/unknown-kind/oversized/bad-version rejection,
MQTT mission downlink contract + dispatched state, outbox
claim→execute→outcome, and persisted restart state.

### Device payload signatures

`GATEWAY_DEVICE_HMAC_KEYS` (JSON `{"<device_id>": "<secret>"}`) enables
HMAC-SHA256 verification of canonical envelopes — same signing as
`sensors/pucks` `Observation.canonical()`. A keyed device whose payload is
unsigned or invalidly signed is rejected; unkeyed devices unaffected.
Verified cross-language: real Python puck signatures validate at the
gateway (17/17 validate tests).
