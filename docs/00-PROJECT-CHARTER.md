# SENTINEL HIVE | Project Charter and Engineer Onboarding

**Version:** Planning baseline v1.0 | **Event:** HackUTD 2026 | **Status:** Design specification, not evidence of implemented functionality.

## Mission

Build a cyber-physical incident response system: a mobile autonomous rover plus three sensing pucks observe a controlled enterprise-office mockup, correlate physical/wireless anomalies with lab network telemetry, use **NVIDIA Nemotron** to plan bounded tool-based investigations, synchronize operational state in **SpacetimeDB**, and coordinate authorized containment through a **Winstead-compliant independently secured incident command center**.

**Winning demo in one sentence:** An unexpected wireless device appears, a sensor detects it, a real robot investigates, the digital twin and RF console show the evidence, the operator approves test-network isolation, and the system verifies and documents the outcome.

## Primary sponsor constraints (NOT optional)

1. **NVIDIA:** Use an actual NVIDIA Nemotron model as an active agent, beyond chatbot replies; demonstrate multi-step planning, real external tools, and a useful completed workflow.
2. **Winstead:** Five required components: secure and isolated; admin-managed access control; standards-inspired live incident documentation; explicitly documented compromised-data scope and status; integrated real-time operator communications. Assume the adversary has access to **all internal systems**. The dashboard must remain independently secure. Security, ease of use under stress, and creativity are judging dimensions.
3. **SpacetimeDB main track:** SpacetimeDB must power primary application functionality, not merely chat or robot movement. Store and synchronize sensor events, incidents, permissions projections, tasks, missions, approvals, and verified outcomes; use transactional reducers and subscriptions.

## Definition of done

- Rover autonomously follows a safe waypoint patrol and investigates a new incident mission; emergency stop and local motor watchdog tested.
- At least two independent real observations (e.g., unknown Wi-Fi AP and cabinet-open switch), not an LLM hallucination, trigger a correlated incident.
- Nemotron calls at least three real allowlisted investigation tools, records evidence and uncertainty, and proposes a bounded response.
- Live 3D digital twin shows rover, office assets, zones, sensor states, selected incident and route; selecting an incident reveals time-correlated image and RF evidence.
- RF console displays genuine Wi-Fi metadata from Kismet-capable capture or ESP32 scanning; a spectrum waterfall is only claimed when backed by an actual frequency-domain SDR sample stream.
- Winstead acceptance checklist in 06-WINSTEAD-COMPLIANCE.md passes, including compromised-enterprise network simulation and stress usability.
- SpacetimeDB performs central state transitions; its real-time subscriptions drive dashboard events, not periodic mocked JSON updates.
- Operator-approved lab-only containment is executed with verification; repeated or forged commands do not re-execute.
- Demo completes three consecutive times, with a clearly labeled simulation fallback.

## Scope and priorities

**P0:** Security control plane; identities/RBAC; incident documentation and scope; real-time chat; event contracts; rover basic patrol; one physical sensor plus RF observation; Nemotron tool loop; SpacetimeDB; operator-approved lab containment; 3D map; repeatable demo.

**P1:** Three independent pucks; richer RF sensing with Kismet; SDR waterfall from actual SDR; forensic photo evidence; richer digital twin interactions; battery telemetry; reconnect recovery.

**P2 / out of sprint:** Auto-deploying pucks; robotic arm; indoor LiDAR SLAM; arbitrary enterprise penetration testing; signal jamming, deauthentication, active RF attacks; LLM-controlled motors; fully unattended destructive containment.

## Team interface and ownership

| Role | Delivers | Depends on |
|---|---|---|
| Hardware / Robotics | Rover, drive firmware, local safety, navigation, camera, pucks | Mission and observation schemas |
| Security / RF | Isolated lab, genuine RF evidence, detection rules, Winstead security tests, containment adapter | Gateway and incident model |
| AI / Backend | Nemotron worker, tool gateway, SpacetimeDB schema/reducers, policies | Trusted event ingestion, security boundaries |
| UI / Integrations | 3D digital twin, RF console, incident documentation, admin access, real-time chat | SpacetimeDB subscriptions and curated evidence APIs |

**Integration owner:** Designate one engineer to control cross-service contract changes. Every merged change affecting a contract must update 04-DATA-AND-INTERFACES.md and have a matching test.

## Engineering conventions

- Monorepo target paths: apps/dashboard; apps/device-gateway; apps/agent-runtime; apps/security-control-plane; spacetimedb; robotics/rover; robotics/firmware; sensors/firmware; packages/contracts; packages/security-policy; infra/lab; tests/{integration,security,e2e}; docs.
- TypeScript for application software and SpacetimeDB module; Python for rover perception/navigation; C/C++ or ESP-IDF for embedded devices.
- UTC ISO 8601 timestamps; UUID or ULID for immutable event IDs; monotonic sequence IDs per device; every correlation retains evidence references.
- No credentials in repo, device firmware source, screenshots, sample configs, or Devpost assets.
- Each component must support health/readiness status; degraded operation must be visible.
- No unreviewed real-world network actions or collection of non-consenting third-party traffic.

## Authoritative documents

1. 06-WINSTEAD-COMPLIANCE.md is the source of truth for Winstead acceptance, overrides any UX convenience.
2. 01-SYSTEM-ARCHITECTURE.md defines trust boundaries and service ownership.
3. 04-DATA-AND-INTERFACES.md defines canonical payloads, reducers and authorization.
4. 02-HARDWARE.md and 03-ROBOTICS-RF.md define physical and measurement contracts.
5. 05-NEMOTRON.md defines agent policies and approved tools.
6. 07-COMMAND-CENTER.md defines 3D digital twin and RF UX.
7. 08-SECURITY-THREAT-MODEL.md defines attacks, mitigations and tests.
8. 09-IMPLEMENTATION-PLAN.md and 10-TEST-AND-DEMO.md define execution and verification.
9. 11-REFERENCES-AND-DECISIONS.md holds sources and open decisions.

## Source of requirements

The team-provided 2026 HackUTD sponsor slide captures are the authority for competition-specific criteria; this repository transcribes and operationalizes them. For official technology APIs, see 11-REFERENCES-AND-DECISIONS.md.

## Definition of P0 vs stretch

An item marked 'planned' must never be presented as implemented. In demo commentary distinguish actual detection, derived correlation, model inference, and operator-authorized effects. Claims about performance require measured repeated runs. 
