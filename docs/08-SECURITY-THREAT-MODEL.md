# Threat Model and Defensive Controls

## Scope and protection goals

Systems: rover/ESP32 sensor pucks; office demo network; untrusted lab endpoint(s); RF capture station; gateway; Nemotron inference worker; SpacetimeDB; independently hosted response dashboard and identity provider. Assets: administrator credentials; incident evidence; communications; containment authorization; network management credentials; device safety and availability.

Adversary for Winstead testing: controls or accesses **every internal office/lab system**, can emit fake telemetry, intercept/replay local traffic, access a compromised lab endpoint and try to pivot to the response command center. We do not claim resistance to full compromise of the independent command center host or its identity provider.

## Trust boundary matrix

| Origin | Destination | Allowed | Enforcement |
|---|---|---|---|
| Sensor/rover | Device collector | Authenticated telemetry only | Separate device identities, TTL, schema, rate limit |
| Untrusted office LAN | Independent dashboard | No direct access | Network isolation/firewall; do not put dashboard on test LAN |
| Collector | SpacetimeDB ingest | Signed/trusted service call | Service identity; event provenance; dedup; private tables |
| Browser | Secure backend | User-authorized operations only | Independent login, RBAC/ABAC, CSRF/session protection |
| Browser | SpacetimeDB | Only approved role-scoped views | Authenticated projection gateway or verified identity filtering |
| Nemotron worker | Agent tools | Allowlisted read/investigate/propose | Tool gateway, argument validation, deny arbitrary shell |
| Agent/browser | Lab containment | Never direct | Server-side approval, allowlist, policy, expiry |
| Action executor | Owned test lab | Limited changes | Lab-dedicated credentials, bounded target list, verification |
| Browser | Evidence store | Only authorized artifacts | Signed short-lived references, access audit |

## Specific threats and tests

1. **Replay or forged sensor events:** Include event UUID, device identity, monotonically increasing sequence, observed and gateway-received timestamps; deduplicate; flag skew. Demonstrate rejecting old/reused IDs.
2. **Prompt injection via logs/OCR/SSID:** Treat SSID, extracted text, transcripts, file names, packet metadata as *untrusted observations*; quote as evidence; never let them redefine tool permissions or system instructions. Test with SSID-like strings that ask the agent to ignore rules.
3. **Rogue API or fake action success:** Executor verifies physical/test-network state independently after action; record proposed/authorized/started/verified statuses separately. Test simulated API 200 where target remains connected; record failure.
4. **Privileged session theft from office workstation:** Control-plane identity must be outside office domain; use dedicated admin devices or stronger auth/MFA. Show office-side session does not grant admin privileges.
5. **Object-level authorization bypass:** Probe incident/evidence IDs across roles/tenants; deny unscoped views and enumerate-sensitive APIs. Test subscription filtering after role change.
6. **MQTT privilege escalation:** mTLS per device or strong scoped tokens; ACL publish to device-specific telemetry topics, never commands/admin. Validate payload sizes and topic names.
7. **Race/retry on containment:** Approval object bound to action hash + target + TTL + initiator; monotonic action state; idempotent execution keyed by action ID; no automatic retries of destructive action without reconciliation.
8. **Compromised network bridge:** Bridge has no database administrator credentials and minimal outbound connectivity; ideally data-only from lab to independent network with a separate, restricted action tunnel.
9. **Privacy and uncontrolled radio collection:** Test only owned hardware/authorized radio environment; minimize identifiers, hash where workable, short retention. No public-network packet payload collection, no deauth/jamming.
10. **Rover safety:** Firmware-level deadman/timeout; E-stop disconnects motor energy; no LLM-to-PWM path; collision testing at low speed; avoid driving near people or tripping hazards.

## Recommended incident evidence provenance

Each evidence record: evidence_id, incident_id, UTC observed_at, received_at, source_device_id, acquisition_method, artifact_sha256, storage_ref, privacy_class, trust_tier (sensor / operator / derived / model), and description. Append-only action log with actor, reason, before/after state and verification result. Hash-chaining can flag edits to exported snapshots but does not make a compromised database immutable.

## Rules for contained actions

- Read-only inspection is auto-permitted for known lab sources after input validation.
- Rover mission launch permitted only for authorized safe waypoints; local controller can always reject unsafe commands.
- Firewall isolation, AP disable, switch-port disable or other disruptive actions require an incident-specific operator approval and scope-bound target in owned lab.
- Remove action credentials from agent process. Credential-bearing action executor must be isolated from model and browser runtimes.
- Block any command not covered by explicit schema; use finite action types, not freeform shell strings.
- On loss of identity, database, audit or relay: **deny write/actuation**, display current system health and stale-data warnings.

## Test plan

- Attack simulation on owned test endpoint only: attempt access to admin dashboard/API and unauthorized reducer, prove denial.
- Prompt-injection SSID / OCR fixture; ensure agent references but does not obey malicious text.
- Disconnect lab LAN; show independent dashboard remains up with accurate disconnected telemetry indicator.
- Revoke responder while chat is open; verify blocked new messages/reads and session/subscription renewal.
- Replay observation and action ID; verify no duplicate mission or containment.
- Unplug or power off rover during motion; watchdog stops motors in bounded safe time.
- Inject sensor clock skew, malformed payload, enormous payload, unknown device identity; fail safely and create diagnostic events.
- Fail containment verification; dashboard and incident must show failure rather than success.

## Deployment security checklist

- [ ] Dedicated trusted management host/network and independent identity source
- [ ] Firewall policy documented and tested, no enterprise-to-management blanket allow
- [ ] TLS everywhere external; secure cookie/session, logout/revoke
- [ ] Strong device identity, MQTT ACLs and event validation
- [ ] Private data store and per-user data-projection enforcement
- [ ] RBAC checked on backend/reducers, not just in React
- [ ] Signed/time-bounded action approval, allowed target set, dedup
- [ ] Evidence metadata + protected artifacts + retention policy
- [ ] Operator chat scoped and authenticated
- [ ] Motor E-stop, local watchdog, low-speed test
- [ ] Logs do not leak keys, SSIDs outside test scope, or personal content
- [ ] Adversarial acceptance suite W01–W05 passes (see 06-WINSTEAD-COMPLIANCE.md)
