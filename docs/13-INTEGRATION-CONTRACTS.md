# 13 — Shared Integration Contracts (frozen for Milestone 1)

Issue #95. This document freezes the contracts that every Milestone 1+
component must honor. It describes what the code **already enforces** —
where code and this document disagree, the code wins and this document
gets a fix PR. Source-of-truth files are cited per section.

Provenance vocabulary (used everywhere): `DEMO` (synthetic fixture),
`REPLAY` (recorded capture), `LIVE` (real device/service measurement).
Simulated data must never be presented as `LIVE`.

## 1. Telemetry / observation envelope (device → gateway → SpacetimeDB)

Canonical envelope — enforced by `services/gateway/src/validate.ts`,
produced by `sensors/pucks` (`Observation.canonical()`):

| Field | Type | Rule |
|---|---|---|
| `schema_version` | int | must equal `1` |
| `event_id` | string | bounded, non-empty; dedupe key |
| `device_id` | string | bounded; **authoritative from MQTT topic** `<prefix>/<device_id>/telemetry` — payload disagreement = forgery reject |
| `seq` | int | per-device monotonic; replay/stale rejected reducer-side |
| `observed_at` | string | ISO-8601, parseable |
| `kind` | string | member of `OBSERVATION_KINDS` (see §5) |
| `zone_id` | string | bounded, non-empty |
| `data` | object | ≤ 8 KiB serialized |
| `signature` | string | optional→required for keyed devices; HMAC-SHA256 hex over the 8 signed fields as sorted-key compact JSON (ASCII-only body; non-ASCII fails verify rather than guessing) |

Packet cap 16 KiB. Device-native shapes (e.g. rover mission-runtime
events without `event_id`/`seq`/`kind`) are normalized by the gateway:
`kind=mission_status`, deterministic `event_id`
(`<device>:<mission>:<command>:<event>:<ts>`), gateway-assigned persisted
per-device `seq`. Valid events land as `trust_tier = gateway_validated`.

## 2. Device record (SpacetimeDB `devices` table)

Enums from `spacetimedb/src/schema.ts` (authoritative):

- `DeviceType`: `puck_wifi | puck_contact | puck_ble | rover | kismet | sdr | camera | other`
- `DeviceStatus`: `online | offline | degraded | fault | unknown`
- `TrustTier`: `device_asserted | gateway_validated | verified`

## 3. Mission command (SpacetimeDB → gateway → rover)

Downlink contract — `services/mission-shim/src/transform.ts` input,
`robotics/rover` requires its own signed form:

- Fields: `schema_version`, `command_id`, `mission_id`, `device_id`,
  `type`, `zone_id`, `waypoint_id`, `expires_at`, `max_speed_mps`.
- `MissionType` (schema): `inspect_zone | patrol | capture_photo | return_home | hold`;
  shim maps to rover-native names (`patrol` → `patrol_route`, etc.).
- Rover-side signature: HMAC-SHA256 over canonical unsigned body;
  `expires_at` is enforced rover-side. Foreign `device_id`, unknown
  type, bad `expires_at`, non-ASCII → rejected (transform.test.ts, 19 checks).
- `MissionState`: `proposed → approved → dispatched → accepted →
  navigating → completed | failed | expired | cancelled`.

## 4. Incident / action / approval (SpacetimeDB + Python services)

- `IncidentStatus`: `new | triage | investigating | containment_pending |
  contained | recovery | resolved | closed | dismissed`.
- `Severity`: `info | low | medium | high | critical`.
- `Confidence`: `unknown | suspected | confirmed` (scope-matrix evidence
  gates preserve `unknown`; RF/AP evidence alone cannot confirm breach).
- `UserRole`: `admin | commander | responder | observer | agent |
  device | executor | gateway` — all authorization is server-side.
- `ActionType`: `isolate_endpoint | block_ssid | revoke_credential |
  disable_switch_port | collect_forensics | quarantine_vlan`.
- `ActionState`: `proposed → pending_approval → approved|rejected →
  enqueued → executing → succeeded|failed → verified | expired | cancelled`.
- `OutboxState`: `pending | claimed | succeeded | failed | dead`.
- Python `apps/containment/policy` proposal adds: `ttl_s`,
  `fingerprint` (HMAC, tamper-evident), separation-of-duties (proposer ≠
  approver), finite action allowlist, expiry/replay/self-approval denial.

## 5. Observation `kind` values

`OBSERVATION_KINDS` (gateway validate.ts) includes device-health and
contact/RF event kinds; puck emitters produce `device_health`,
`wifi_observation`, `cabinet_contact_*`, `ble_observation` (see
`sensors/pucks/src/puck_core/`). Frontend `ObservationKind` (demo only):
`unknown | impersonation | tamper | correlated` — UI fixture vocabulary,
NOT a backend contract.

## 6. Frontend adapter boundary (`apps/dashboard/twin/src/command/adapters.ts`)

`SourceEnvelope<T>`: `{ source: 'mock'|'ros2'|'kismet'|'nemotron',
provenance: 'DEMO'|'REPLAY'|'LIVE', sequence, timestamp, payload }`.
Interfaces: `ROS2ReadAdapter`, `KismetReadAdapter`,
`NemotronTransport`, `RoboticsCommandGateway` (server must validate
identity/policy/geofence/E-stop). `DEMO_ADAPTERS` is intentionally empty
until issue #98.

## 7. Confirmed Milestone-1 blockers

| # | Blocker | Evidence | Owner |
|---|---|---|---|
| B1 | `services/gateway` integration test + `src/index.ts` need generated `bindings/` (requires `spacetime` CLI + published module) and a running SpacetimeDB + `GATEWAY_TEST_TOKENS` + seeded lab | `test/gateway.test.ts` header; `ERR_MODULE_NOT_FOUND: bindings/index` | **done (#97)** — bindings generate via `npm run generate`; compose stack + seed verified; test 17/17 |
| B2 | `spacetimedb` `test:smoke` needs `spacetime` CLI (not installed) + server; `tsc --noEmit` passes | `package.json` scripts | **done (#97)** — CLI pinned to server version (deploy/README); smoke 44/44 on scratch DB via `SPACETIMEDB_DATABASE` |
| B3 | `spacetimedb/package-lock.json` was out of sync with package.json (missing `tsx`) — **fixed in this PR** via `npm install` lock regen | `npm ci` EUSAGE | done (#95) |
| B4 | `network_wand_code` expects `backend/app.py` (`POST /api/wand`) — absent from repo | `network_wand_code/config.yaml` | #117 |
| B5 | Frontend `DEMO_ADAPTERS` empty — no live backend connection | `adapters.ts:13` | #98 |
| B6 | `autonomy/` has no automated test suite (sim entrypoint only; imports verified) | `autonomy/` | #115/#117 |
| B7 | `network_wand_code/hw_test.py` requires physical Wi-Fi hardware | file header | #117 |
| B8 | npm advisories (34 entries, 13 high) unresolved | `VALIDATION.md` | #118 |

## 8. Verification record (this issue)

- Python pytest: **233 passed, 0 failed** across 26 packages
  (apps/agent×3, containment×3, control_plane, identity, security_tests,
  incident_records, incident_chat, scope_matrix, glue×6, rf_intel,
  ops_ux, ops/demo+chaos_harness, robotics/rover, sensors×3).
- TS services: mission-shim **19/19**; gateway validate **17/17**;
  gateway integration **BLOCKED (B1)**; spacetimedb typecheck clean,
  smoke **BLOCKED (B2)**.
- Frontend: vitest **23/23**, `tsc --noEmit` clean, `vite build` OK.
- `autonomy/` modules import cleanly; no test suite exists (B6).
