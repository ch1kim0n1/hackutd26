# Architecture — SENTINEL HIVE

## Trust zones
1. **Untrusted office lab:** ESP32 pucks, rover Pi/ESP32, test AP, lab endpoint, Kismet receiver and optional SDR. Assume attacker controls all internal lab systems.
2. **Constrained collector:** validates device identity, schema, sequence, time, size, and rate; relays outbound to independent management network. Lab devices never access management DB or administrator sessions directly.
3. **Independent Winstead command plane:** separately hosted dashboard, independent identity, role policy, SpacetimeDB, team chat, evidence object storage, policy enforcer and restricted action executor.
4. **AI worker:** NVIDIA Nemotron uses allowlisted investigation tools, with read-only evidence access and narrow rover mission requests. It cannot approve or execute network containment.

## System event pipeline
Sensor/Rover/Kismet -> authenticated MQTT/collector -> validation and dedup gateway -> SpacetimeDB observation reducer -> deterministic correlation -> incident -> Nemotron tool investigation -> rover mission -> evidence artifacts + data summaries -> command center subscription -> authorized human approval -> scoped lab action executor -> independent verification -> incident audit, scope and chat update.

## Component ownership
| Component | Runtime | State/input | Output |
|---|---|---|---|
| Rover MCU | ESP-IDF C++ | validated speed/TTL, encoder, obstacle/E-stop | odometry and stopped/fault |
| Rover Pi | Python/OpenCV | missions, camera, AprilTags | pose, evidence references |
| Pucks | ESP32 | scan schedule, switch, BLE | signed/scoped observations |
| RF collector | Kismet + optional SDR | compatible real radio input | Wi-Fi metadata, IQ-derived FFT frames |
| Gateway | Node/TypeScript | raw device reports | authenticated normalized events |
| SpacetimeDB | TypeScript module | reducers and tables | authoritative transactional state + subscriptions |
| Agent | Nemotron, TypeScript worker | incident context, tool registry | observations, hypothesis, approved mission, proposals |
| UI | React + R3F | authorized live views | 3D twin, RF console, incidents, admin/chat |
| Lab executor | separate secured service | scoped approved action | verified lab-only result |

## Deployment rules
- Do not host dashboard on compromised test LAN; independent operator identity and trusted management origin.
- Private evidence stays in object store; only refs and hashes in SpacetimeDB.
- Sensitive DB tables private. Server enforces per-role, per-incident view access; never trust disabled React buttons.
- Side effects are executed by a durable outbox worker after reducer records an approved action; no external firewall calls inside DB transactions.
- Mission actions bounded to surveyed waypoints and capped speed; local motor watchdog and emergency stop independent of network and LLM.
- Dashboard remains useful when rover/model unavailable; when DB/identity/policy fails, freeze disruptive actions, show stale status.
- Every claim in demo separated into observed / derived / AI inferred / operator-approved / independently verified.

## Nonfunctional initial targets (to be measured)
Sensor-to-command center median under 2s on test LAN, start-to-incident under 5s, model-first-action under 15s if API healthy, three complete repeatable demos. These are targets, not measured guarantees.
