# SENTINEL HIVE — HackUTD 2026

**Autonomous cyber-physical defense platform** | NVIDIA Nemotron × Winstead × SpacetimeDB

A mobile security rover and wireless/physical sensor network observe an **owned mock enterprise office**. A Nemotron agent performs real, auditable multi-step investigation; SpacetimeDB synchronizes device and incident state; an **independently secured** Winstead incident command center lets authorized operators document scope, communicate, approve limited lab response, and verify results.

> **Current state: design documentation only.** This repo is the main engineering source of truth; implementation, security compliance and measured performance are not yet verified.

## Read first

1. [Project charter / ownership / definition of done](docs/00-PROJECT-CHARTER.md)
2. [Architecture and trust boundaries](docs/01-SYSTEM-ARCHITECTURE.md)
3. [**Winstead's exact required components and pass/fail tests**](docs/06-WINSTEAD-COMPLIANCE.md) — **mandatory**
4. [Implementation sprint and team work allocation](docs/09-IMPLEMENTATION-PLAN.md)
5. [Test matrix and live demo runbook](docs/10-TEST-AND-DEMO.md)

## Engineering reference

| Domain | Spec | Owner focus |
|---|---|---|
| Hardware, power, safety, procurement | [02-HARDWARE](docs/02-HARDWARE.md) | Robotics/hardware |
| Rover navigation and RF collection | [03-ROBOTICS-RF](docs/03-ROBOTICS-RF.md) | Robotics + security |
| State, reducers, typed messages | [04-DATA-AND-INTERFACES](docs/04-DATA-AND-INTERFACES.md) | Backend |
| NVIDIA Nemotron agent / tools | [05-NEMOTRON](docs/05-NEMOTRON.md) | AI engineer |
| React + Three.js twin, RF console, command UX | [07-COMMAND-CENTER](docs/07-COMMAND-CENTER.md) | Frontend |
| Attack boundaries and defenses | [08-SECURITY-THREAT-MODEL](docs/08-SECURITY-THREAT-MODEL.md) | Security |
| References and decisions | [11-REFERENCES-AND-DECISIONS](docs/11-REFERENCES-AND-DECISIONS.md) | Everyone |

## Three challenge mappings

- **NVIDIA:** real Nemotron agent; evidence-based planning, tools and bounded missions beyond chatbot output.
- **Winstead:** five hard requirements: isolated security; admin user management; live incident documentation; explicit compromised-data scope; integrated real-time team chat. **Assume attacker access to all internal office systems**—trusted command plane must remain independently secure. See [full checklist](docs/06-WINSTEAD-COMPLIANCE.md).
- **SpacetimeDB:** central transactional engine and real-time subscriptions driving sensors, missions, incidents, evidence, permissions projections, approvals and response state. Not merely chat/robot movement.

## Core physical demonstration

1. Owned unknown Wi-Fi AP appears near mock cabinet; sensor detects unfamiliar BSSID, cabinet contact opens.
2. Gateway validates real observations, creates correlated incident through SpacetimeDB.
3. Nemotron inspects inventory and RF evidence, requests safe rover inspection.
4. Rover navigates to known waypoint, captures time-stamped evidence.
5. 3D twin shows mission/incident; RF console shows **actual Wi-Fi channel activity** and evidence provenance. True SDR FFT waterfall is optional and requires actual IQ capture.
6. Authorized Commander and Responder use incident-specific live chat, data-impact scope matrix, and auditable approval flow.
7. Executor isolates only allowlisted owned lab endpoint, verifies outcome, and stores timeline and evidence manifest.

## Important security / safety rules

No general network attacks, wireless deauth/jamming, arbitrary LLM-run shell, direct LLM motor control, or unapproved disruptive containment. The rover must have independent E-stop + watchdog; office network is untrusted. No claim of proven exfiltration from Wi-Fi anomalies. Simulations/replays must be labeled.

## Contribution protocol

- Read the relevant spec and Winstead security checks **before** coding.
- API/schema changes require simultaneous update to [04-DATA-AND-INTERFACES](docs/04-DATA-AND-INTERFACES.md).
- Security/UX changes require testing against [06-WINSTEAD-COMPLIANCE](docs/06-WINSTEAD-COMPLIANCE.md).
- Implementation must record test outcomes with evidence; descriptions in docs are not proof.
- Resolve hardware part numbers, identity host, model endpoint and SDK versions in [open decisions](docs/11-REFERENCES-AND-DECISIONS.md).

**Source:** HackUTD 2026 sponsor slide photographs provided by the team, with vendor API references linked in docs. Sponsor participation and cross-track submission policy require independent confirmation.
