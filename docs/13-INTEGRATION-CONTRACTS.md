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

`OBSERVATION_KINDS` (gateway validate.ts ≡ spacetimedb lib.ts — keep in
sync) includes device-health, contact/RF event kinds, and the
data-center node telemetry kinds below; puck emitters produce
`device_health`, `wifi_observation`, `cabinet_contact_*`,
`ble_observation` (see `sensors/pucks/src/puck_core/`). Frontend
`ObservationKind` (demo only): `unknown | impersonation | tamper |
correlated` — UI fixture vocabulary, NOT a backend contract.

### Data-center node telemetry (added for the virtual Pi fleet)

`apps/datacenter` emits these kinds inside the SAME canonical envelope
(`schema_version`, `event_id`, `device_id` from topic, per-device `seq`,
`observed_at`, `kind`, `zone_id`, `data`, optional `signature`). Future
physical Raspberry Pi monitoring agents MUST use this identical
contract — kind names and `data` shapes are the stable interface:

| kind | `data` shape (objective fields only — no verdict labels) |
|---|---|
| `device_health` | `{status: ok\|degraded\|fault\|stale, note, firmware, recovered?: true, ...}` — `recovered: true` marks a revive/heal signal |
| `service_inventory` | `{listeners: [{name, port, proto, version, expected}], unexpected: [{name, port, proto}]}` — `unexpected` = listeners outside the node's own baseline |
| `network_flow` | `{src, dst, proto, dst_port?, packets, bytes, duration_s, direction?, distinct_dst_ports?, flags?}` — NetFlow-style facts; classification is the correlator's job |
| `resource_metric` | `{cpu_pct, mem_pct, load1, interval_s}` — pure metrics; high CPU alone is NOT an anomaly |
| `config_drift` | `{key, baseline, live, resolved}` — config-vs-baseline diff report |
| `temperature` | `{celsius, sensor}` (pre-existing) |

Correlation (`spacetimedb/src/lib.ts`) is data-aware for these kinds:
`device_health` correlates on `data.status` (`ok` heartbeats never
alert), `service_inventory` on non-empty `unexpected`, `config_drift`
on `resolved !== true`, `network_flow` on objective thresholds
(≥8 distinct dst ports, ≥64 MiB, or known-bad dst port). Recovery
signals (`device_health` ok+`recovered`, `config_drift` resolved,
clean `service_inventory`) resolve matching open auto-alerts and move
linked incidents to `recovery` when the lifecycle permits.
`resource_metric`, `temperature`, and benign flows produce no
alert/incident. Attack-scenario ground truth lives in
`apps/datacenter/artifacts/*/ground_truth.json` — evaluation-only,
never published to MQTT/SpacetimeDB and never visible to Nemotron.

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

## 9. Twin spatial feed contracts (frontend-implemented; backend transport pending)

The dashboard twin consumes two versioned payload contracts, implemented
in `apps/dashboard/twin/src/command/twin/occupancyContract.ts`. They are
**frontend contracts**: the dashboard parses, validates, and renders them
today, but no backend currently emits them — producing them is a
documented integration request, not a competing API.

### `sentinel.rover.occupancy_grid` v1

```json
{
  "contract": "sentinel.rover.occupancy_grid",
  "schema_version": 1,
  "frame_id": "surveyed_floorplan",
  "resolution_m": 0.25,
  "width": 96, "height": 72,
  "origin": { "x": 0.0, "y": 0.0 },
  "revision": 12,
  "timestamp": "2026-11-07T18:42:00.000Z",
  "cells": [-1, 0, 100, "..."],
  "anchors": [{ "id": "pi-edge-01", "x": 21.0, "y": 6.0, "label": "PI-EDGE-01" }]
}
```

- `cells` is row-major (`cells[iy * width + ix]`), length `width*height`.
- Cell semantics follow ROS OccupancyGrid: `-1` unknown, `0` free,
  `100` occupied; intermediate values are probability classified at the
  50 threshold. **Normalization:** if every value lies in `[-1, 1]` the
  array is treated as legacy normalized `0..1` probability and scaled
  ×100 — deterministic and identical for the existing demo grid
  (threshold 0.5 ≡ 50).
- `origin` is the frame_id-space coordinate of cell (0,0)'s lower-left
  corner; cell (ix,iy) spans `[origin + i·res, origin + (i+1)·res)`.
- `revision` is monotonic per `frame_id`; `timestamp` versions each
  snapshot. The twin keeps the newest revision per frame (timestamp
  breaks ties) and flags maps stale after 30 s without an update.
- `anchors` are registered surveyed positions (puck/Pi-class devices)
  in the map's frame; unregistered-frame anchors are dropped, never
  silently placed.
- Limits: ≤512×512 dims, ≤262,144 cells, ≤500 m extent — enforced at
  parse time so malformed payloads cannot allocate unbounded geometry.

### `sentinel.rover.pose_report` v1

```json
{
  "contract": "sentinel.rover.pose_report",
  "schema_version": 1,
  "device_id": "rover-01",
  "x": 3.0, "y": 4.0, "theta": 1.25,
  "unit": "m",
  "frame_id": "surveyed_floorplan",
  "timestamp": "2026-11-07T18:42:00.000Z",
  "provenance": "SIM"
}
```

- `x`/`y` in metres (`unit: "mm"` accepted, divided by 1000); `theta`
  in radians CCW from frame +x (also accepts `heading_rad`/`yaw`).
- Fixes merge into the same stream as `mission_status` observation
  poses — newest timestamp wins; staleness (>5 s) zeroes speed and
  flags the rover.

### Frame registration

`registerFrame()` in `occupancyContract.ts` is the only transform the
twin applies: `surveyed_floorplan`/`facility`/`floorplan` are identity,
`autonomy_map` gets the documented static sim-room offset
(`AUTONOMY_MAP_OFFSET = {x:12, y:9}`, same as `live/map.ts`), and any
other `frame_id` is **unregistered** — geometry keeps its raw
coordinates behind an amber UNREGISTERED boundary and is never silently
placed on the facility map (docs/14: autonomy and surveyed frames are
not comparable without alignment).

### Transport paths (frontend adapters only)

1. **Embedded contracts** — payloads nested inside observation
   `dataJson` (depth ≤5, carrier keys `occupancy_grid`/`pose_report` or
   bare `contract` discriminators) ride the frozen telemetry pipeline
   today, bounded by the 8 KiB envelope cap — suitable for pose reports
   and small maps.
2. **Dedicated feed** — `TwinFeedTransport` in `live/twin.ts`:
   `SimTwinTransport` (DEMO/REPLAY-labelled, used by fixture mode and
   `?twin=sim`) and `HttpTwinTransport` polling `VITE_TWIN_FEED_URL`
   (`GET` → `{maps?, poses?, anchors?|registered_devices?}`). **Backend
   request:** expose a read-only twin feed endpoint serving these
   contract payloads; the frontend is already wired for it.

### Rendering semantics

- Occupied cells merge into deterministic maximal rectangles rendered
  as instanced boxes. **Heights are INFERRED presentation estimates**
  (deterministic per rect identity, 0.35–1.3 m) — never LiDAR or
  surveyed measurements; the UI labels them as such.
- Instance slots persist by rect key (`OccupancyInstanceSet`), so a
  revision that changes a few cells rewrites only affected instances.
- Unknown cells render as low ground plates (unmapped ≠ free); free
  cells show the facility floor.
- Map +x → world +X, map +y → world −Z (three.js Y-up), identical to
  the existing `mapToWorld` convention — occupancy geometry, rover
  pose, Pi anchors, devices, and incident markers share one
  coordinate system.
