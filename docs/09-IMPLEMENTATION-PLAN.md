# Implementation Plan / Parallel Engineering Tasks

## Priority and critical path
**P0 path:** trusted management plane + auth -> SpacetimeDB schema / incident CRUD/chat -> normalized device event ingestion -> deterministic anomaly -> Nemotron tools -> safe rover inspection -> human approval and action executor -> verified incident timeline -> 3D twin. Do not save Winstead security work until after visual polish.

### Phase 0 — Pre-build preparation (before timed sprint)
- [ ] Confirm actual physical BOM, power safety, test lab APs, USB radios, independent trusted host.
- [ ] Confirm NVIDIA Nemotron available endpoint and sample tool call; pin model ID/terms.
- [ ] Confirm SpacetimeDB SDK/runtime and private table / view access mechanics with actual version.
- [ ] Bring up independent identity demo with two browser sessions; validate lab-to-management deny.
- [ ] Create office mini-map with surveyed waypoints, AprilTags, measured zones.
- [ ] Validate GitHub repo docs and assign per-component owners.

### Phase 1 — First integration vertical slice
- [ ] Create schema/reducers: device, observation, alert, incident, scope, evidence, chat, approval, audit, mission.
- [ ] Build device gateway with telemetry identity, schema and dedup.
- [ ] Send real cabinet reed switch event -> live incident -> two authorized browsers see state.
- [ ] Implement Admin add/revoke roles plus tests. Ensure roles enforced on backend and subscriptions.
- [ ] Implement chat with incident-specific room membership and offline/reconnect behavior.

### Phase 2 — Robot and sensors
- [ ] Assemble/verify rover rails, motor controller, E-stop, local watchdog, encoders and camera.
- [ ] ESP32 puck A Wi-Fi channel observation; puck B physical contact; puck C BLE known beacon optional.
- [ ] Rover execute predefined patrol, stop and inspection waypoints; return mission telemetry.
- [ ] Capture photo to protected artifact store; evidence metadata with SHA-256 and zone.
- [ ] Run anomaly correlation and incident state changes through SpacetimeDB.

### Phase 3 — AI and incident response
- [ ] Nemotron service observes incident and calls real inventory, RF, cabinet, rover mission tools (minimum 3).
- [ ] Enforce JSON schemas, prompt-injection defenses, bounded tool count, timeouts, audit and incident provenance.
- [ ] Create scoped containment proposal bound to exact target/action hash; Commander approval.
- [ ] Independent executor applies lab firewall/test switch policy and verifies connectivity; write immutable-ish audit events.
- [ ] Populate data-compromise scope model and explicitly show unknown vs confirmed impact.

### Phase 4 — Wow UI (after compliance path works)
- [ ] React/R3F 3D office model with rover position, path, sensors, threat locations.
- [ ] Clickable incident linking image, radio observations and agent reasoning.
- [ ] Wi-Fi Channel Activity interface with real Kismet/ESP32 observations.
- [ ] Optional SDR FFT waterfall only if actual compatible IQ sensor and signal processing ready.
- [ ] Stress UX run: unfamiliar responder gets to evidence/chat/scope with minimal instructions.

### Phase 5 — Security hardening and demo
- [ ] Execute every W01–W05 test from docs/06; record proof.
- [ ] Simulate attacker control of test LAN while management console remains secure and operational.
- [ ] Validate RBAC revocation, duplicate events, prompt injection, offline robot and executor action failure.
- [ ] Repeat full end-to-end three times with screenshots, screen recording, logs and stopwatch.
- [ ] Freeze P0, fix regressions, prepare fallback recorded run labeled REPLAY.

## Suggested sprint time (4 engineers, ~24h, adjust to event)
0–3h: isolated control plane, bench rover, schema; 3–7h: incident CRUD/chat and sensors; 7–12h: rover inspection and Nemotron; 12–17h: approval/execution/scope and 3D; 17–21h: RF visuals/integration; 21–24h: security tests, rehearsals, submission.
Parallel owners: hardware/robotics; cyber/security/RF; AI/backend/SpacetimeDB; frontend/integration. Integration owner approves schema changes.

## Backlog breakdown (epic → acceptance)
E1 independent management/auth -> lab attacker cannot access control plane; admin can add/revoke.
E2 SpacetimeDB -> all primary states and chat live, role-scoped.
E3 devices -> real authenticated sensor packets and safe rover mission.
E4 RF -> live real Wi-Fi metadata; optional true SDR IQ waterfall.
E5 agent -> Nemotron real multi-step tool evidence and bounded mission.
E6 Winstead -> documentation, compromised-data scope, incident chat, admin console, isolated command center.
E7 action -> approval, allowlisted lab isolation, independent verification.
E8 3D twin -> dynamic telemetry + selected incident evidence drawer.
E9 proof -> tests, demo, provenance and robustness.
E10 optional puck deployment and robotic arm only after all E1–E9 pass.

## Merge criteria
Tests for changed contracts, no secrets, lint/typecheck pass, docs updated, UI labels truthful, no bypass of security policy, reviewer confirms correct Winstead R01–R05 mapping. Never merge a feature that disables authorization or hardware failsafes to make a demo easier.
