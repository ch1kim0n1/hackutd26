# 14 — Rover Mission Contract (sentinel.rover.* v1)

**Status:** frozen for issue #115 (M5.1). Supersedes nothing; *extends* the
frozen envelopes of [13-INTEGRATION-CONTRACTS.md](13-INTEGRATION-CONTRACTS.md)
with the rover mission/telemetry/evidence vocabulary shared by `autonomy/`,
`robotics/rover/`, `services/mission-shim/`, and `spacetimedb/`.

**Test vectors:** [`contracts/rover/fixtures/`](../contracts/rover/fixtures/)
(`missions.json`, `telemetry.json`, `evidence.json`) are consumed verbatim by
all three implementations — Python (`rover_mission/common.py`,
`autonomy/mission_map.py`) and TypeScript (`mission-shim/src/common.ts`). If a
stack drifts, its suite fails against the same JSON.

---

## 1. The problem this solves

Three rover stacks evolved separately and spoke three different dialects:

| Stack | Mission form | Telemetry form | Evidence form |
|---|---|---|---|
| `spacetimedb` module | `commandJson` (reducers-mission.ts) | `MissionState` projection only | evidence rows (schema.ts) |
| `services/mission-shim` | module `commandJson` → signed rover mission | — | — |
| `robotics/rover` | signed `Mission` dict + HMAC | `_emit` event payloads | `EvidenceRef` + sidecar `.json` |
| `autonomy/` | none (Brain modes only) | `{pose:[x,y,th], mode}` POST | none |

Nothing defined how a mission *type*, *state*, or *pose* means the same thing
across them. This document freezes one canonical vocabulary plus explicit,
tested mappings — without changing any existing on-the-wire format.

## 2. Common contracts (all `schema_version: 1`)

Four envelope contracts. `contract` is the discriminator; every object is a
plain JSON dict. All string fields must be ASCII — non-ASCII breaks the
byte-identical canonical JSON the HMAC signature depends on.

| Contract | `contract` value | Produced by | Consumed by |
|---|---|---|---|
| Mission | `sentinel.rover.mission` | module leg, rover ingest, autonomy directive echo | shim, rover, autonomy, tests |
| Telemetry | `sentinel.rover.telemetry` | rover `_emit`, autonomy report, module status | gateway normalization, twin, tests |
| Evidence | `sentinel.rover.evidence` | rover artifact store, sidecar meta | evidence rows, twin, tests |
| Autonomy directive | `sentinel.rover.autonomy_directive` | `common_to_directive` (advisory only) | autonomy runtime binding (#116) |

### 2.1 `sentinel.rover.mission` — the union envelope

Required for **every** mission: `contract`, `schema_version`, `mission_id`,
`command_id`, `device_id`, `type`, `expires_at` (ISO-8601 UTC). Optional:
`zone_id`, `waypoint_id`, `route_id`, `camera_id`, `max_speed_mps` (>0),
`issued_at`.

Per-type requirements are a **union**, deliberately looser than any single
consumer — each boundary enforces its own subset:

| `type` | Common-level requirement | Module leg additionally requires |
|---|---|---|
| `inspect_zone` | `zone_id` + `waypoint_id` | same + speed ∈ (0.05, 0.5] |
| `patrol` | `waypoint_id` **or** `route_id` | `zone_id` + `waypoint_id` + speed window |
| `capture_photo` | — | `zone_id` + `waypoint_id` + speed window |
| `return_home` | — | `zone_id` + `waypoint_id` + speed window |
| `hold` | — | `zone_id` + `waypoint_id` + speed window |
| `wireless_rescan` | `zone_id` | **never module-dispatchable** |

`patrol` is the only type with an any-of selector: `waypoint_id` is the
*module/shim selector* (resolved to a surveyed `route_id` via shim config),
`route_id` is the *resolved authority* (rover-native form). Explicit
`route_id` always wins over config resolution.

### 2.2 `sentinel.rover.telemetry`

`contract`, `schema_version`, `event` (free-form event name), `device_id`,
`observed_at`, `provenance` ∈ {`DEMO`, `REPLAY`, `LIVE`} (frozen by doc 13 —
simulated data is never `LIVE`). Optional: `mission_id`, `command_id`,
`type` (common mission type), `state` (common state), `zone_id`,
`waypoint_id`, `reason`, `pose`, `data` (free-form extras bag).

### 2.3 `sentinel.rover.evidence`

`contract`, `schema_version`, `artifact_id`, `mission_id`, `device_id`,
`zone_id`, `observed_at`, `storage_ref`, `sha256` (64 lowercase hex),
`bytes` (int ≥ 0), `synthetic` (bool), `provenance`. Optional:
`command_id`, `waypoint_id`, `camera_id`, `received_at`, `pose`, `width`,
`height`, `format`.

`synthetic: true` ⇒ provenance defaults to `DEMO` unless explicitly
overridden — sim evidence is never presented as `LIVE`.

### 2.4 `sentinel.rover.autonomy_directive`

Advisory behavior hint for the autonomy stack: `contract`,
`schema_version`, `mission_id`, `command_id`, `device_id`, `behavior`,
`mission_type`, `timeout_s` (derived from `expires_at`), `expires_at`,
optional `issued_at`, `zone_id`, `waypoint_id`, `route_id`,
`max_speed_mps`, `route_ref`, `waypoints` (resolved refs), and flags
`capture` / `rescan` / `checkpoint`.

`behavior` uses the brain.py vocabulary (`PATROL`, `CHECKPOINT`,
`RETURN_HOME`, `STOP`, plus autonomy-native `EXPLORE`, `COVER`,
`WALL_FOLLOW`). `mission_type` is **mandatory for round-trips** — behavior
alone is lossy (`inspect_zone`/`patrol` share `PATROL`-family behaviors,
`capture_photo`/`wireless_rescan`/`inspect_zone` share `CHECKPOINT`).

## 3. Field transport matrix — what each leg carries

| Field | module `commandJson` | rover mission | autonomy directive |
|---|---|---|---|
| `issued_at` | ✗ | ✗ | ✓ |
| `route_id` | ✗ | ✓ (patrol_route only) | ✓ |
| `camera_id` | ✗ | ✓ (capture_photo only) | ✗ |
| `zone_id`,`waypoint_id` | ✓ required | type-dependent | ✓ when present |

Consequences, all pinned by fixtures:

- `module_command → common` **loses** `issued_at`, `route_id`, `camera_id`.
- `common → rover mission` requires the **module leg** for
  `inspect_zone`, `patrol` (without explicit `route_id`), `capture_photo`,
  `return_home`, `hold` — i.e. `zone_id` + `waypoint_id` + speed ∈
  (0.05, 0.5]. The shim only signs what the module could have authorized.
- `rover mission → common → rover mission` is a **fixed point** only for
  `inspect_zone`, `patrol`, `wireless_rescan` — the rover forms that carry
  the module-required fields. `capture_photo`, `return_home`, `hold` are
  marked `rover_form_lossy` in fixtures: the rover object drops
  `zone_id`/`waypoint_id`, so a rover-derived common is no longer
  module-dispatchable and the second leg correctly refuses. The module
  path remains the only authority for them.
- `autonomy directive → common` loses `camera_id` (autonomy has no camera).

## 4. Mission-state reconciliation

Common `state` vocabulary = union of module `MissionState` and rover
`MissionState` (13 values). **Device-reportable** states — the only ones
`recordMissionResult`/`applyMissionStatus` accept — are exactly
`accepted`, `navigating`, `completed`, `failed` (`DEVICE_STATES` in
reducers-mission.ts, `MISSION_STATUS_DEVICE_STATES` in lib.ts).

| Common/rover state | Module device report | Notes |
|---|---|---|
| `accepted` | `accepted` | |
| `navigating` | `navigating` | |
| `scanning` | `navigating` | rover sub-phase of navigating; native name kept in telemetry `state`, projection collapses it |
| `completed` | `completed` | |
| `failed` | `failed` | |
| `aborted` | `failed` + reason `aborted:<native>` | e.g. `aborted:estop_asserted` |
| `timed_out` | `failed` + reason `timed_out:<native>` | e.g. `timed_out:waypoint_timeout` |
| `queued` | — (no report) | module mission stays `dispatched` until rover accepts |
| `proposed`,`approved`,`dispatched` | — | module-side lifecycle, never device-reported |
| `expired`,`cancelled` | — | module-side terminal states |

`module_report_fields(state, reason)` in `common.py`/`common.ts` is the
single implementation of this table. Native outcomes are **never**
silently upgraded: `aborted`/`timed_out` project to `failed` with the
native name preserved in the reason string.

**Known gap (documented, not fixed):** before this contract, rover
`aborted`/`timed_out`/`scanning`/`queued` events had no legal path into the
module projection — `applyMissionStatus` silently skips non-device states.
Mission uplink now has an explicit projection (`module_report_fields`), but
**no reducer was changed**: wiring the gateway to call it is integration
work owned by the gateway/backend stack, tracked as a follow-up. Until then
a rover abort still cannot advance a module mission past `dispatched` —
this is a real operational gap, not a cosmetic one.

## 5. `wireless_rescan` — device-local by design

The module `MissionType` enum has no rescan type and **no schema change was
made** (reducers-mission.ts is frozen upstream contract). `wireless_rescan`
is the single device-local extension:

- Common type exists; `zone_id` required; `waypoint_id` optional.
- `common → module command`: **refused** (`None`) — it can never be
  module-dispatched.
- `common → rover mission`: **allowed** via the device-local leg — same
  envelope, same HMAC signature rules, same `mission_contract.py`
  validation at ingest (surveyed zone/waypoint whitelist still enforced
  rover-side). It rides the same signed-command channel as module missions.
- `rover → autonomy directive`: `CHECKPOINT` behavior + `rescan: true`.

Who may originate it: any producer holding the mission HMAC secret and
targeting a surveyed zone — in practice the rover-local tooling or a
backend job with device credentials. It is *not* Nemotron-originated:
model output still cannot reach actuators (agent guards unchanged).

## 6. autonomy/ boundary

`autonomy/mission_map.py` is a **self-contained stdlib port** of the common
schema — autonomy deploys to the Pi as flat scripts and cannot import
`rover_mission`. `test_autonomy_parity.py` asserts every shared table and
every fixture verdict matches `rover_mission/common.py` exactly.

- `common → directive`: advisory only. `timeout_s = expires_at - now`;
  `waypoints` resolved from an optional waypoint table; behavior flags
  (`capture`/`rescan`/`checkpoint`) mark evidence-adjacent intents.
- `directive → common`: only mission-typed directives map back;
  autonomy-native behaviors (`EXPLORE`, `COVER`, `WALL_FOLLOW`) return
  `None` — they are not missions.
- `{pose, mode}` reports → `pose_report` telemetry: pose converted to
  `{x, y, heading_rad, unit:"m", frame:"autonomy_map"}` — **never
  comparable to rover poses** (`unit:"mm"`, `frame:"surveyed_floorplan"`).
  Frame alignment is #116's problem, not this contract's.
- **Onboard navigation is unchanged**: `run.py`'s 10 Hz loop, `brain.py`
  modes, LiDAR/scan-match, and E-stop/watchdog are untouched. Directives
  are advisory inputs a runtime binding may consume; they carry no
  authority over motors. Nemotron remains centralized — nothing here puts
  inference in the motor loop.

## 7. Compatibility findings (what already existed vs. what was missing)

| Finding | Resolution |
|---|---|
| Module device states ⊊ rover states (`scanning`,`aborted`,`timed_out`,`queued` unreportable) | §4 projection table + `module_report_fields`; reducers unchanged |
| `wireless_rescan` unreachable via module | §5 device-local leg, no schema change |
| `commandJson` drops `issued_at`/`route_id`/`camera_id` | §3 transport matrix; documented, fixtures pin it |
| Rover `capture_photo`/`return_home`/`stop` forms drop `zone_id`/`waypoint_id` | §3 `rover_form_lossy`; module remains sole authority |
| `pose_confidence` top-level field duplicates `pose.confidence` | folded into `pose.confidence` in common telemetry |
| Rescan `EvidenceRef`s have empty `path`/`sha256`/`bytes` | **not evidence** — scan markers; `evidence_to_common` rejects them (fixture `rescan-marker-not-evidence`) |
| autonomy `{pose,mode}` POST had no contract | `pose_report` telemetry + `autonomy_directive` (this doc) |
| `autonomy/` had no tests | `autonomy/tests/test_mission_map.py` (new) |

## 8. What did NOT change

- `spacetimedb/src/reducers-mission.ts`, `schema.ts`, `lib.ts` — frozen.
- `services/gateway` — no normalization changes (its `mission_status`
  normalization already accepts these event shapes).
- `robotics/rover` navigation, `mission_contract.py` validation, HMAC,
  telemetry publishers, E-stop/watchdog — unchanged; `common.py` is
  additive.
- `autonomy/run.py`, `brain.py`, `sim.py` — unchanged; `mission_map.py` is
  additive.
- Python API facade, Nemotron client, agent guards — untouched (other
  Devins' scope).

## 9. Files

- `robotics/rover/src/rover_mission/common.py` — canonical Python impl
  (validators + all mappers + `module_report_fields`).
- `autonomy/mission_map.py` — self-contained parity port (directive +
  report legs only; no module leg by design).
- `services/mission-shim/src/common.ts` — TS impl; `commonToRoverMission`
  reuses `transform.ts` for the module leg.
- `contracts/rover/fixtures/*.json` — shared test vectors.
- Tests: `robotics/rover/tests/test_common_contract.py`,
  `test_autonomy_parity.py`, `autonomy/tests/test_mission_map.py`,
  `services/mission-shim/test/common.test.ts`.
