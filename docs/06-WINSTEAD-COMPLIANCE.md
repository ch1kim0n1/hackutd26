# Winstead | Mandatory Cyber Incident Response Dashboard Contract

**Highest-priority engineering acceptance document.** This document tracks the sponsor slide closely and converts each phrase into concrete implementation and adversarial tests. A visually impressive rover cannot compensate for missing requirements. Status of every item is **NOT YET VERIFIED** until tests are recorded.

## Source transcription: challenge and judging

**Challenge:** Build a Cyber Incident Response Dashboard designed to act as a **command center** during and after a cyber incident.

**Required 01 — Secure and Isolated:** "The system should be highly secure and should operate inside potentially compromised networks as an isolated system."

**Required 02 — Access Control:** "Administrative ability to add individuals to the platform."

**Required 03 — Incident Documentation:** "Ability to enter details of the incident in a manner that reflects the standards for cyber incident documentation. Account for real-time updating and status monitoring."

**Required 04 — Scope Definitions:** "Related to incident documentation, but specifically documenting the range of data that has been compromised and the status of the compromised data (locked for ransomware, exfiltrated, etc.)."

**Required 05 — Real-Time Communications:** "Account for real-time communications within the dashboard."

**Judging — Security:** "The assumption must be that the attacker has access to all internal systems. The dashboard must be independently secure."

**Judging — Ease of Use:** Team members enter under stress, likely without tutorials; intuitive operation matters.

**Judging — Creativity:** Features beyond the basic dashboard that enhance functionality.

Prizes shown: $1,500 / $900 / $300 per team for 1st / 2nd / 3rd.

## Design premise / hostile environment

Assume the office/test-lab network is hostile, endpoints are compromised, and the attacker can read or alter internal traffic, use stolen internal-host credentials, and disrupt office services. **Do not** assume the attacker has already compromised independently controlled operator identities, hardware security roots, or the separate response control plane; if these also fall, no dashboard can guarantee security.

**Independent response control plane** (logical/physical separation):
- Host response dashboard, authentication and authorization, evidence metadata, SpacetimeDB, and operator chat on a management segment / independent trusted host **not on the enterprise lab LAN**.
- The compromised lab is an untrusted *data source*. Use outbound-only collector relays where possible; do not allow lab inbound network access to response control plane.
- One constrained bridge/gateway to the lab is permitted for allowlisted observations and approved actions; enforce segmentation, mTLS or tightly scoped service credentials, strict origin checks, network ACLs and egress filtering.
- Operator logins must not rely on corporate domain controllers or authentication sessions obtainable from the compromised lab. Pre-provision independent identities (OIDC provider outside lab or local independently managed IdP with MFA as feasible).
- Fail closed for authorization and actuation if identity, policy, logging or approval check unavailable. Dashboard may remain read-only using cached state, clearly marked stale.

## R01 — Secure and Isolated (must pass ALL)

Implementation:
- Separate management and compromised lab networks; document exact VLAN/router/firewall boundaries and show blocked path by default.
- Terminate TLS for browser/UI, backend, WebSocket subscriptions and chat; encrypt device relay traffic; do not expose SpacetimeDB management or MQTT unauthenticated.
- Keep sensitive SpacetimeDB tables private; serve role-limited incident projections after authorization. Never subscribe browsers to a table containing secrets, full unredacted evidence, or unrelated incident data.
- Device gateway accepts only signed/authenticated and schema-validated observations; sensor telemetry is NOT an instruction.
- API denies direct calls to rover motion or containment from the browser; must go through a policy-enforced service.
- No shared API keys in frontend or devices; secret rotation and revoke tested. No default admin password.
- Explicitly restrict file uploads and evidence retrieval; no execution of evidence contents; treat logs/camera OCR as untrusted.

Acceptance tests:
- W01a: On a simulated compromised enterprise workstation, attempt dashboard admin access, SpacetimeDB subscription, chat channel, sensor gateway, and actuation APIs; each denied without separate credentials.
- W01b: Disable enterprise DNS, DHCP or IdP / disconnect office LAN; independent dashboard and operator chat continue (if management connectivity remains).
- W01c: Replay captured lab-origin telemetry and issue forged command; duplicate dropped and command denied.
- W01d: Operator token expires or is revoked; privileged operation denied immediately.
- W01e: A direct browser request to a containment endpoint without server-side approval is refused.
- Evidence: network topology, service access matrix, screenshots/video, test logs, test runner outcome.

## R02 — Access Control (must pass ALL)

Roles:
- **Admin:** Invite/add/revoke users; assign/revoke roles; manage incident assignments and policies; cannot bypass two-person approval if enabled.
- **Incident Commander:** Create incidents, assign responders, change lifecycle, propose/approve bounded lab containment (separate initiator rule when configured).
- **Responder:** Document, upload evidence, discuss, propose containment; no user management.
- **Observer:** Read-only authorized incident access; no evidence upload or writes.
- **Device/Agent identities:** Non-interactive service principals with narrowly scoped reducer/tool access, not human roles.

Implementation:
- Admin UI: Add user (email/username or independently issued account), choose role and incident scope; list users, suspend, revoke, audit each action.
- Server-side authorization for every reducer, view/aggregation, upload, WebSocket event and artifact fetch; client-disabled buttons are not a security control.
- Default deny; least privilege; avoid assigning roles based on user-supplied client claims.
- Rate limits and account lockout or step-up verification; secure session termination.
- Demo seeded Admin, Commander, Responder, Observer test identities with **separate independent credentials**.

Acceptance tests:
- W02a: Admin adds and revokes a responder; audit trail confirms actor and timestamp.
- W02b: Observer cannot invoke incident mutation, read unrelated incident or fetch restricted evidence by guessing ID.
- W02c: Responder cannot add users or approve own requested action when separation is required.
- W02d: Revocation takes effect for new subscriptions and actions (invalidate/reconnect existing sessions).
- W02e: Device credentials cannot log in as humans.

## R03 — Incident Documentation (must pass ALL)

Model fields, strongly typed:
- Incident ID, title, summary, severity (critical/high/medium/low), confidence, source, evidence references.
- First seen / created / last updated / detected / contained / resolved timestamps (UTC).
- Reporter, incident commander, assignees, affected locations and assets, impact assessment, indicators (with provenance).
- Incident state: New, Triage, Investigating, Containment Pending, Contained, Recovery, Resolved, Closed, Dismissed.
- Timeline events and linked response actions with actor, reason, outcome, timestamps and trace/correlation IDs.
- Explicit uncertainty fields: suspected/confirmed and evidence gaps. Model output may propose but cannot overwrite human-confirmed facts silently.
- Minimal standards-inspired incident record structure: preparation, detection/analysis, containment, eradication/recovery, post-incident lessons learned; NIST SP 800-61 Rev. 3 may be used as reference, but do not claim audit certification.

UI:
- Incident creation and edit form accessible in 2 clicks from incident list.
- Real-time status indicator with last-update time; concurrent edits use version checks and present conflicts, not silent overwrite.
- Visible ownership, actions pending approval, and next recommended step.

Acceptance:
- W03a: Responders create, edit, assign, annotate, attach evidence and close a sample incident.
- W03b: Two different users see the same state changes live without refresh.
- W03c: Timeline preserves prior values and actors; failed actions are visibly failed, not reported complete.
- W03d: Export one complete incident packet (JSON or Markdown plus referenced evidence manifest) with attribution and UTC timestamps.
- W03e: Explain a recovered/dismissed incident rather than forcing every anomaly into 'confirmed breach'.

## R04 — Scope Definitions and Compromised Data (must pass ALL)

This is distinct from generic incident severity. Implement explicit **data exposure/availability scope**:
- Entities: asset/system, business unit/location, dataset/data category, estimated record count, impact window and owner.
- Per-scope status enum: **unknown, suspected exposed, confirmed exposed, exfiltrated, encrypted/locked, corrupted, unavailable, contained, restored, unaffected**. Allow multiple impact dimensions (confidentiality, integrity, availability) rather than a single mutually exclusive flag.
- Source of evidence; confidence; first/last known affected timestamps; containment status; reviewer; last updated.
- Visual impact matrix: Assets × CIA effects; no inference of exfiltration solely from a rogue AP.
- Track changing scope as new evidence arrives. Explicitly display 'unknown / not assessed', never equate blank with safe.
- Anomaly scenario: a rogue SSID and cabinet-open alert can establish **suspected physical/wireless compromise**, while **confirmed data exfiltration remains none/unverified** unless demonstrable evidence exists.
- For showing ransomware and exfiltration examples, use **synthetic fixtures on test VMs only**; do not encrypt or extract real customer data.

Acceptance:
- W04a: Commander edits compromised-data scope while responders see updates live.
- W04b: Create separately a simulated exfiltration case and a simulated locked-data case; their scope statuses and estimated impact differ visibly.
- W04c: Asset and data statuses are independently editable, evidence-linked and auditable.
- W04d: Report distinguishes suspected exposure from confirmed exfiltration.
- W04e: Scope updates preserve earlier snapshots in audit history.

## R05 — Real-Time Communications (must pass ALL)

Build incident-specific **team chat inside the dashboard**, not merely email notification.
- Authenticated rooms per incident plus optional incident-command channel; sender name/role, UTC time, membership, message ID, delivery status.
- Live presence/connection state; unread counts; pinned operational updates; incident-linked message deep links.
- All room membership checks server-side; messages retained through reconnect, with audit/export policy.
- System posts for agent mission, approval request, approval outcome, verified containment; visually distinguish bot and human messages.
- No untrusted rich HTML or executable attachments; sanitize input and preview safely.
- On connectivity loss, show disconnected state and retry without duplicate messages; do not claim messages delivered while offline.

Acceptance:
- W05a: Commander and responder exchange messages across separate browsers with observable low latency.
- W05b: Unauthorized observer cannot join restricted incident room or post.
- W05c: User reconnects and receives missing messages; duplicate client retries do not cause multiple posts.
- W05d: System status message contains a link to relevant action/evidence.

## Judging quality gates

**Security demonstration:** show office-lab 'compromise' from untrusted test endpoint, then prove dashboard remains independent; attack attempts fail while logged.
**Ease-of-use demonstration:** new teammate has 60 seconds with no instructions to find a live incident, read scope, assign themselves, message team, and locate the approval (role-appropriate).
**Creativity:** 3D digital twin, live RF sensing, physical autonomous robot and real containment with clear evidence chain. These are additions, **not substitutes** for any requirement.

## Demo sequence for Winstead judges

1. Reveal independently hosted command center URL and seeded role-specific users; show user add/revoke via Admin.
2. Simulate compromise of office-side endpoint and attempt unauthorized console access; demonstrate failure.
3. Create correlated incident using physical sensor plus RF observation; live timeline and documentation appear.
4. Open Scope tab; show explicit affected assets, data categories and **unknown**/suspected impact, not fabricated exfiltration.
5. Commander and responder exchange real-time messages; demonstrate system mission and alert posts.
6. Approve isolated test-device containment; verify execution, reason and audit history; export incident packet.

## Evidence checklist (keep beside demo)

- [ ] W01a–e isolation and attack tests recorded
- [ ] W02a–e RBAC and admin tests recorded
- [ ] W03a–e incident documentation tests recorded
- [ ] W04a–e compromised-data scope tests recorded
- [ ] W05a–d communications tests recorded
- [ ] Screenshots: Users, Incident Timeline, Scope Matrix, Chat, Audit, Security topology
- [ ] Screen recording: independent control plane survives lab compromise
- [ ] Human demo operator can complete flow without instructions

## Explicit exclusions and honesty boundaries

No fake 'real-time' animated incident state without SpacetimeDB updates. No claim of confirmed exfiltration from RF observation alone. No control panel hosted solely inside compromised test network. No admin-only access hidden in the backend without an actual add-user UI. No claim of Winstead compliance until all W-tests have been run. 
