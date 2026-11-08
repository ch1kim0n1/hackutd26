# Rover mission runtime (Raspberry Pi)

Python service that executes authorized missions on the rover: surveyed
waypoint navigation, AprilTag/odometry localization, camera evidence capture
with SHA-256 artifacts, and mission state telemetry. Contracts:
`docs/04-DATA-AND-INTERFACES.md`; behavior: `docs/03-ROBOTICS-RF.md`.

## Layout

| Module | Role |
|---|---|
| `mission_contract.py` | docs/04 mission validation — **local, autonomous rejection** of unsafe/invalid/forged commands before anything reaches motors |
| `auth.py` | HMAC-SHA256 mission signatures (secret via `ROVER_MISSION_SECRET`, never in repo) |
| `routes.py` + `config/routes.json` | surveyed waypoint/zone/route whitelist — the ONLY places the rover may go |
| `navigator.py` | turn-in-place/straight control law over whitelisted waypoints; obstacle/estop/link-loss gating |
| `localization.py` | ESP32 odometry fusion + AprilTag correction with confidence tracking |
| `motor_link.py` | ESP32 serial protocol client (`Esp32SerialLink`) + `SimulatedLink` for tests/sim |
| `camera.py` | `Cv2Camera` (real) / `SyntheticCamera` (honestly labeled sim) + `ArtifactStore` (image + JSON sidecar, sha256, retention) |
| `telemetry.py` | mission event publishers: HTTP gateway / MQTT / console |
| `inspection.py` | registered Pi targets (`config/inspection_targets.json`), `InspectionReport` evidence model, hashed report store |
| `netinspect.py` | `NetworkInspector` seam — `SimulatedNetworkInspector` (deterministic scenarios) + `LiveNetworkInspector` (allowlisted targets/checks, bounded timeouts) |
| `hw_adapter.py` | autonomy compatibility adapter — `inspect_zone` checkpoint → `{mission_id, action: inspect_cabinet, cabinet_id}`; simulated transport default, live transport reserved/unbound |
| `service.py` | `RoverService` — queue, state machine, evidence, abort/expiry, checkpoint inspection |
| `cli.py` | `python -m rover_mission …` |

## Mission lifecycle

`queued → accepted → navigating → (dwell|capture|rescan) → completed | failed | aborted | timed_out`

Mission types (docs/03): `patrol_route`, `inspect_zone`, `capture_photo`,
`wireless_rescan`, `return_home`, `stop`.

Validation rejects: bad schema, wrong device, missing per-type fields,
unknown route/waypoint/zone/camera, expired `expires_at`,
`max_speed_mps > 0.25`, duplicate `mission_id`/`command_id` (idempotent
ingest), and any bad/missing HMAC signature — **all locally,
with zero motor commands issued** (tested).

## Checkpoint network inspection (inspect_zone)

After an `inspect_zone` mission finishes its waypoint actions (capture /
rescan / dwell), the rover enters an `inspect` checkpoint phase:

1. `(zone_id, waypoint_id)` resolves to a **registered Pi** in
   `config/inspection_targets.json` — surveyed waypoints without a
   registration report `no_registered_target`, never a guessed target.
2. The configured `NetworkInspector` runs allowlisted health checks
   (`ping`, `tcp_connect`, `http_health` — bounded ports/paths only) and
   attaches simulated wireless observations (`wifi_ap_seen`, `wifi_probe`,
   `device_health`/`device_offline`).
3. A structured `InspectionReport` (incident_id, mission_id, target
   device_id, UTC timestamps, checks, observations, provenance,
   `synthetic` flag) is written to `evidence/inspection/<zone>/insp-*.json`
   + `.meta.json` sidecar (sha256 + storage_ref), mapped through
   `sentinel.rover.evidence` (`evidence_to_common`) and announced via
   `inspection_started` / `inspection_completed` mission telemetry.

Adapters: `SimulatedNetworkInspector` is the default (deterministic,
`provenance: DEMO`, `synthetic: true`). `LiveNetworkInspector` performs
real bounded probes (`ROVER_INSPECTOR=live`) but **only** against
registry-allowlisted addresses and re-validated check specs — anything
else is denied before a packet is sent. Stale results
(`inspection_max_age_s`) are flagged `stale`, never silently trusted.
Inspection outcomes are evidence, not mission failures: an unreachable Pi
or sensor fault completes the mission with an honest report.

```sh
# live (bounded, allowlisted) inspection probes — opt-in only
ROVER_INSPECTOR=live ROVER_MISSION_SECRET=… \
    python3 -m rover_mission run-mission mission.json
```

### Hardware autonomy adapter (`ROVER_INSPECTOR=hardware`)

`hw_adapter.py` maps the authorized `inspect_zone` checkpoint to the
physical autonomy command contract:

```json
{"mission_id": "inspection-001", "action": "inspect_cabinet", "cabinet_id": "rack-02"}
```

- `cabinet_id` comes only from the target's registered `cabinet_id` in
  `config/inspection_targets.json` — re-validated against the registry
  allowlist before a command is built. Never derived from camera markers,
  AprilTag payloads, or sticker types.
- `mission_id` is preserved verbatim for correlation/dedup; responses
  echoing a different `mission_id` or `cabinet_id` are recorded as error
  evidence, never merged.
- `SimulatedHardwareTransport` (default) returns deterministic canned
  responses (`provenance: DEMO`, `synthetic: true`). `ROVER_HARDWARE_TRANSPORT=live`
  is reserved for the hardware engineer's autonomy link — until bound it
  refuses closed rather than pretending.
- Responses normalize into the same `InspectionReport` evidence
  (mission_id, cabinet_id, target device_id, timestamps, provenance,
  evidence_refs) through the hashed artifact store + telemetry path.

```sh
ROVER_INSPECTOR=hardware ROVER_MISSION_SECRET=… \
    python3 -m rover_mission run-mission mission.json
```

## Commands

```sh
pip install -e '.[dev]'          # or: PYTHONPATH=src pytest

# 5 collision-free patrols on the simulated link (evidence run)
PYTHONPATH=src python3 -m rover_mission simulate-patrols 5 \
    --evidence-dir evidence/patrol-run

# validate / execute a signed mission file
ROVER_MISSION_SECRET=… python3 -m rover_mission validate mission.json
ROVER_MISSION_SECRET=… python3 -m rover_mission run-mission mission.json
```

Real hardware: set `ROVER_TELEMETRY_URL`/`MQTT_*` for event shipping,
`Esp32SerialLink(port="/dev/ttyUSB0")` for the motor link, `Cv2Camera()` +
AprilTag detector for real pose correction.

## Tests

```sh
cd robotics/rover && python3 -m pytest tests/ -q
```

202 tests: contract rejections (forgery, expiry, overspeed, unknown
fixtures, duplicate missions), patrol/inspect/rescan/return-home/stop
execution, checkpoint network inspection (success, unregistered targets,
unreachable devices, stale results, sensor failures, live-adapter
allowlist + bounded probes), hardware autonomy adapter (command shape,
cabinet allowlist, simulated responses, mismatch/timeout/duplicate/stale
handling, end-to-end wiring), evidence hashing, abort, E-stop abort,
mission timeout, navigator obstacle/estop/timeout.

## Evidence & honesty

- `evidence/patrol-run/` — five simulated patrols, all `completed`,
  4 hashed artifacts each. **Simulated link + synthetic camera frames —
  labeled `synthetic: true` in every artifact; NOT physical proof.**
- Physical acceptance (H03/H09 patrols, H04/H07 camera) requires the real
  rover per `hardware/bring-up-checklist.md`.
- `config/routes.json` coordinates are PLACEHOLDERS pending H06 survey
  calibration; replace with measured waypoints before floor tests.
