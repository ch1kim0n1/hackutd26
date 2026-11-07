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
| `service.py` | `RoverService` — queue, state machine, evidence, abort/expiry |
| `cli.py` | `python -m rover_mission …` |

## Mission lifecycle

`queued → accepted → navigating → (dwell|capture|rescan) → completed | failed | aborted | timed_out`

Mission types (docs/03): `patrol_route`, `inspect_zone`, `capture_photo`,
`wireless_rescan`, `return_home`, `stop`.

Validation rejects: bad schema, wrong device, missing per-type fields,
unknown route/waypoint/zone/camera, expired `expires_at`,
`max_speed_mps > 0.25`, and any bad/missing HMAC signature — **all locally,
with zero motor commands issued** (tested).

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

28 tests: contract rejections (forgery, expiry, overspeed, unknown
fixtures), patrol/inspect/rescan/return-home/stop execution, evidence
hashing, abort, E-stop abort, mission timeout, navigator obstacle/estop/
timeout.

## Evidence & honesty

- `evidence/patrol-run/` — five simulated patrols, all `completed`,
  4 hashed artifacts each. **Simulated link + synthetic camera frames —
  labeled `synthetic: true` in every artifact; NOT physical proof.**
- Physical acceptance (H03/H09 patrols, H04/H07 camera) requires the real
  rover per `hardware/bring-up-checklist.md`.
- `config/routes.json` coordinates are PLACEHOLDERS pending H06 survey
  calibration; replace with measured waypoints before floor tests.
