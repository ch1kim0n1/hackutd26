# Phantom Command

A complete local cybersecurity command center for the **Phantom Patrol** autonomous rover. Six connected workspaces share a deterministic simulation: **Sense → Detect → Analyze → Investigate → Visualize → Report**.

Everything is explicitly **DEMO MODE**. No hardware, network scanner, inference service, account, database, API key, or external HTTP request is required. State is in memory and resets on reload.

## Run

```sh
cd apps/dashboard/twin # from the repository root
npm ci
npm run dev
```

Open the URL Vite prints, normally `http://127.0.0.1:5173/`. `/` is the project landing page; the console itself opens at `/#overview` (any workspace hash or `?live=` query goes straight to it). Supported Node versions: 22.13+, 24 LTS, or 26+; npm 10+. The verified environment is Node 26.12.1 / npm 11.20.0 on macOS arm64.

## Demo walkthrough

1. Leave **Autonomous resolution** selected, choose **4×** or **8×**, and press **Start simulation**.
2. At simulation time +3 seconds, an unknown BLE signature is observed. The mock agent correlates identity and location, opens an incident, checks policy, and dispatches a bounded inspection.
3. Watch the rover travel through the mapped corridors in **Digital Twin**. The affected zone, incident timeline, activity trace, and telemetry update together.
4. The rover collects synthetic RF, camera, and LiDAR evidence. The agent reconciles it against the service fixture, publishes its conclusion, and resolves the incident automatically. No AI prompt is needed.
5. Choose **AP impersonation** to demonstrate a separate operator approval for simulated isolation. Inspect the evidence in **Incident Center** or approve/reject in **Nemotron Intelligence**. No real network action is sent.

Pause freezes the deterministic clock; Resume continues it; Reset restores the chosen scenario. Scenarios include normal patrol, unknown transmitter, AP impersonation, cabinet tampering, correlated anomalies, and autonomous resolution. **Inject event** introduces additional structured observations; analysis proceeds when the clock is running.

Emergency stop independently latches rover movement and evidence capture while facility monitoring continues. Capture resumes with its remaining active time after **Release stop**; it cannot finish just because the facility clock advanced while stopped. Return home cancels existing missions and queues a home route; it never clears E-stop. An interrupted incident can be reassigned from its dossier with **Reassign inspection**. Checkpoints and the LiDAR map support bounded operator waypoints.

## Workspaces

| Workspace | Implemented behavior |
|---|---|
| Command Overview | Shared posture/incident/device metrics, interactive twin preview, live agent feed, ECharts telemetry, incident watch, rover status, movable/resizable React Grid Layout panels |
| Digital Twin | Occupancy-grid extrusion, 3 zones, 12 racks, 4 APs, 3 monitors, rover geometry, actual mission routes, RF overlays, threat markers, selected entities, isometric/top/orbit/follow cameras and manual orbit |
| Network Intelligence | AG Grid search, protocol/state filters, sorting, linked selection, RSSI history, risk scores, 32-device React Flow topology and observation stream |
| Incident Center | Automatic/manual incident creation, severity/status filtering, linked evidence, findings, timeline, related devices, location focus, reassignments and approval history |
| Rover Operations | Procedural synthetic camera, LiDAR map, waypoint dispatch, battery/position/speed/distance, mission queue, telemetry, E-stop and return home |
| Nemotron Intelligence | Automatic activity trace, correlation, tool records, findings/confidence, mission decisions, current selection context, policy and human approval controls |

`⌘K` / `Ctrl+K` opens entity/workspace search. Selection persists across workspaces, and operator-created incidents update shared agent context immediately, even before the clock starts. Every workspace has a hash URL (for example, `/#network`); sidebar, search and in-panel navigation support browser Back/Forward and reload. Returning to overview restores the isometric camera. The optional **Context console** uses CopilotKit with a local AG-UI transport to summarize the current shared records; it does not call an LLM. The original integration gallery remains at `/lab.html`; the original JSX demo remains at `/legacy.html`.

## Architecture

- `src/command/model.ts`: typed entities, stable identifiers, separate observations/evidence/findings and UI selection contracts.
- `fixtures.ts`: 32 entities, historical context, fixed UTC epoch and deterministic telemetry.
- `engine.ts`: pure immutable simulation transitions, fixed 250 ms steps, bounded grid route planner, mission lifecycle and evidence pipeline.
- `agents.ts`: structured `MockAgentProvider`, tool registry, policy decisions, shared context store, and a validated future `NemotronAgentProvider`.
- `event-bus.ts` / `store.ts`: typed event publication and shared Zustand state. UI actions and simulation transitions use one path.
- `navigation.ts`: synchronizes workspace state with deep links and browser history, including cleanup on unmount.
- `adapters.ts`: ROS 2 pose subscription, Kismet observation/inventory, structured Nemotron transport, and a server-authorized robotics gateway interface. No adapters are connected in demo mode.
- `twin/`: occupancy conversion, merged wall geometry, rendering, camera control and accessible entity controls.
- `workspaces/`, `components/`: product UI, common primitives, GSAP numeric transitions, Motion navigation/activity transitions and secondary CopilotKit context.

Map coordinates are metres: +x → world X, +y → world −Z, vertical → world Y. Zone bounds are `[minX, minY, maxX, maxY]`. The facility is 24×18 m. World geometry comes from a 0.25 m occupancy grid; route planning uses a 0.5 m navigable grid. UI interpolation never modifies observed simulation coordinates.

## Verify

```sh
npm run check                 # ESLint, Vitest, strict TypeScript, production build
npx --no-install playwright install chromium # first browser setup only
npm run test:ui               # full application + retained laboratory/legacy regressions
npm run preview              # serve the production build
npm run licenses             # refresh dependency inventory and retained notices
```

See [VALIDATION.md](VALIDATION.md) for results and known dependency advisories. Browser tests run against the production build, exercise the full autonomous flow, record console errors and external requests, and cover small-desktop/mobile layouts and reduced motion. Screenshots and failure traces are saved in ignored `test-results/`.

The scene caps DPR at 1.5, uses procedural geometry without downloaded models/textures/fonts, merges occupancy cells, and uses low-intensity bloom without multisampling. Reduced motion disables entrance transitions, numeric tweening, scan pulses and camera interpolation. All visual states also have textual controls and status information.

## Real-service integration

Keep the demo as a deterministic contract fixture. Implement the typed adapters behind authenticated server boundaries and translate real source timestamps/frames explicitly. Validate schemas, provenance, authorization, geofences, robot watchdogs and E-stop on the backend. Model output may propose actions; it must not directly actuate hardware or authorize containment. Replace CopilotKit's demo-only in-memory transport with an authenticated runtime when that backend exists.

This deliverable is a complete **simulated frontend**, not a deployment of ROS 2, Kismet, Nemotron inference, production identity, or sponsor compliance. The procedural camera and LiDAR displays are synthetic illustrations, not hardware reconstructions. Large optional CopilotKit/Three/AG Grid chunks and current transitive dependency advisories are recorded in [VALIDATION.md](VALIDATION.md). Retain [THIRD_PARTY_NOTICES.txt](public/THIRD_PARTY_NOTICES.txt) with distributed builds. GSAP uses its standard no-charge license; see the exact licenses in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Live backend mode (issue #98)

The header DEMO/LIVE switch toggles between the deterministic simulation and live backend feeds.

- **DEMO** (default): unchanged offline simulation — scenarios, injection, approvals, rover commands.
- **LIVE**: read-only view of SpacetimeDB role-scoped views (`src/command/live/`) plus the Python API facade (#96). Demo-mutating controls are disabled; the simulation clock keeps advancing so backend timestamps map to elapsed time correctly.

Configuration (`.env.local`, see `.env.example`):
- `VITE_SPACETIMEDB_URI` / `VITE_SPACETIMEDB_DATABASE` / `VITE_SPACETIMEDB_TOKEN` — provisioned identity token (admin sees all incidents; see `deploy/seeds/seed.ts` → `deploy/secrets/identities.json`).
- `VITE_API_BASE` / `VITE_API_POLL_MS` — FastAPI facade for health + investigation activity.
- `VITE_LIVE_TRANSPORT=fixture` or `?live=fixture` — replays recorded rows labelled **REPLAY** (tests/offline demos).

Live entities carry `LIVE`/`REPLAY` provenance prefixes in generated detail text — never conflated with DEMO. Entity collections are rebuilt wholesale from subscribed views on every update, so reconnect/resync/refresh cannot duplicate rows; the mode choice persists in `localStorage` (`phantom-command-mode`).

Unimplemented surfaces (later issues): live command path (approvals/missions/waypoints go through the backend outbox, not this UI), per-device RF telemetry, rover pose telemetry, API-universe incidents (separate store from SpacetimeDB incidents), Nemotron inference (#111).

## Optional physical rover camera

The Rover Operations camera panel can display the rover camera service over an SSH tunnel while the rest of the demo stays simulated. With an authenticated SSH connection to the rover, run this from the repository root in a dedicated terminal (replace `david@ROVER_IP` and the remote path as needed):

```sh
ssh -L 127.0.0.1:18080:127.0.0.1:18080 david@ROVER_IP \
  'python3 -u - 18080 http://127.0.0.1:5188 /home/david/camera_service.py' \
  < deploy/scripts/rover-camera-loopback.py
```

This launches the rover's existing service on loopback and restricts CORS to the given dashboard origin. In another terminal, start Vite using that same origin:

```sh
VITE_ROVER_CAMERA_URL=http://127.0.0.1:18080 npm run dev -- --port 5188 --strictPort
```

The setting accepts only `http://127.0.0.1:<port>` or `http://localhost:<port>`. The service must provide `/health` with a recent `timestamp_utc` and `frame_age_s`, plus `/stream.mjpg`; the rover's existing camera service supports these endpoints. The panel reports stale or unavailable feeds instead of silently switching to simulated video. Camera access does not connect mission dispatch, LiDAR mapping, emergency stop, or other rover controls. Never expose the unauthenticated camera service to the network; use the SSH tunnel.
