// Mission bridge — connects the investigator orchestrator's queued action
// requests to the AUTHORIZED SpacetimeDB mission path, and mirrors
// auto-correlated SpacetimeDB incidents to the Nemotron orchestrator.
//
//   SpacetimeDB incidentFeed (commander view)
//     -> resolve zone/device via alert -> observation
//     -> POST /internal/events  (API agent token)   => Nemotron investigates
//     -> grantIncidentAccess(agent, responder)      => agent may propose
//
//   API GET /internal/mission-requests (agent token)
//     -> dedupe vs missionFeed (repeat investigations must not re-fly)
//     -> proposeMission (agent identity, responder-scoped)
//     -> mission 'proposed' -> PATCH request state
//     -> [human commander approves via approveMission — never automated here]
//     -> missionFeed tracks approved/dispatched/.../terminal
//     -> terminal: attachEvidence(report) + POST inspection_evidence event
//        => follow-up Nemotron assessment consumes real evidence
//
// Least privilege: agent conn proposes + attaches evidence; commander conn
// only grants access and watches feeds. Approval stays a human reducer call.
//
// Run:  cd services/gateway && npx tsx ../mission-bridge/src/index.ts
// (reuses gateway's generated bindings + node_modules)
//
// Env:
//   SPACETIMEDB_URI / SPACETIMEDB_DATABASE
//   AGENT_SPACETIMEDB_TOKEN      — 'agent' role identity (propose/attach)
//   COMMANDER_SPACETIMEDB_TOKEN  — incident commander (grants + feeds)
//   API_BASE                     — e.g. http://127.0.0.1:8000
//   API_AGENT_TOKEN              — API agent machine token (SENTINEL_AGENT_TOKEN)
//   ROVER_DEVICE_ID              — default rover-01
//   MISSION_TTL_S                — proposal expiry (default 600, cap 840 < 15min module max)
//   MISSION_MAX_SPEED_MPS        — default 0.2 (module caps at 0.5)
//   ROVER_EVIDENCE_DIR           — rover inspection artifact root
//   POLL_MS                      — request/status poll cadence (default 1500)

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
// Reuses the gateway's generated bindings + node_modules (run via
// `npx tsx` from services/gateway). 'spacetimedb' resolves there only.
import { DbConnection } from '../../gateway/bindings/index';

/** Identity rows come from the SDK as `any`-ish view rows; we only need
 * to pass the value back into grantIncidentAccess verbatim. */
type AgentIdentity = any;

const URI = process.env.SPACETIMEDB_URI ?? 'ws://127.0.0.1:3000';
const DB = process.env.SPACETIMEDB_DATABASE ?? 'sentinel-hive';
const AGENT_TOKEN = process.env.AGENT_SPACETIMEDB_TOKEN ?? '';
const CMD_TOKEN = process.env.COMMANDER_SPACETIMEDB_TOKEN ?? '';
const API_BASE = process.env.API_BASE ?? 'http://127.0.0.1:8000';
const API_AGENT_TOKEN = process.env.API_AGENT_TOKEN ?? '';
const ROVER_DEVICE = process.env.ROVER_DEVICE_ID ?? 'rover-01';
// Module cap is 15min (MISSION_MAX_TTL_MICROS); stay under it for clock skew.
const MISSION_TTL_S = Math.min(Number(process.env.MISSION_TTL_S ?? 600), 840);
const MISSION_MAX_SPEED = Number(process.env.MISSION_MAX_SPEED_MPS ?? 0.2);
const EVIDENCE_DIR = process.env.ROVER_EVIDENCE_DIR ?? '';
const POLL_MS = Number(process.env.POLL_MS ?? 1500);
const MAX_PROPOSE_ATTEMPTS = 5;

if (!AGENT_TOKEN || !CMD_TOKEN) {
  console.error('AGENT_SPACETIMEDB_TOKEN and COMMANDER_SPACETIMEDB_TOKEN are required');
  process.exit(2);
}
if (!API_AGENT_TOKEN) {
  console.error('API_AGENT_TOKEN is required');
  process.exit(2);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const log = (o: Record<string, unknown>) => console.log(JSON.stringify({ svc: 'mission-bridge', ...o }));

// ---------------------------------------------------------------------------
// SpacetimeDB connections
// ---------------------------------------------------------------------------

function connect(token: string): Promise<DbConnection> {
  return new Promise((resolve, reject) => {
    DbConnection.builder()
      .withUri(URI)
      .withDatabaseName(DB)
      .withToken(token)
      .withAutomaticReconnect()
      .onConnect((c) => resolve(c))
      .onConnectError((_ctx, e) => reject(e))
      .build();
  });
}

const FEED_VIEWS = ['incidentFeed', 'opsAlertFeed', 'observationFeed', 'missionFeed', 'myAccess'] as const;

function subscribe(conn: DbConnection, views: readonly string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    conn.subscriptionBuilder()
      .onApplied(() => resolve())
      .onError((ctx: any) => reject(ctx?.error ?? ctx))
      .subscribe((tables) =>
        views.map((v) => (tables as Record<string, { build(): unknown }>)[v].build() as never));
  });
}

const agent = await connect(AGENT_TOKEN);
const cmd = await connect(CMD_TOKEN);
await subscribe(agent, ['missionFeed', 'myAccess']);
await subscribe(cmd, [...FEED_VIEWS]);
log({ event: 'connected', uri: URI, db: DB });

// Agent's own SpacetimeDB identity (needed for grantIncidentAccess userId).
let agentIdentity: AgentIdentity | null = null;
for (let i = 0; i < 50 && !agentIdentity; i++) {
  const rows = [...(await agent.db.myAccess.iter())];
  agentIdentity = rows[0]?.userId ?? null;
  if (!agentIdentity) await sleep(200);
}
if (!agentIdentity) {
  console.error('could not resolve agent identity via myAccess');
  process.exit(2);
}
log({ event: 'agent_identity', id: agentIdentity.toHexString() });

// ---------------------------------------------------------------------------
// API helpers (agent machine token)
// ---------------------------------------------------------------------------

async function api(path: string, init?: RequestInit): Promise<any> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${API_AGENT_TOKEN}`,
      ...(init?.headers ?? {}),
    },
    signal: AbortSignal.timeout(5000),
  });
  if (!res.ok) throw new Error(`api ${path} -> ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

async function postInvestigationEvent(ev: Record<string, unknown>): Promise<string> {
  const r = await api('/internal/events', { method: 'POST', body: JSON.stringify(ev) });
  return String(r?.data?.status ?? r?.status ?? 'unknown');
}

async function patchRequest(rid: string, state: string, missionId = '', detail = ''): Promise<void> {
  await api(`/internal/mission-requests/${encodeURIComponent(rid)}`, {
    method: 'POST',
    body: JSON.stringify({ state, mission_id: missionId, detail }),
  });
}

// ---------------------------------------------------------------------------
// Incident mirroring: SpacetimeDB incident -> orchestrator investigation
// ---------------------------------------------------------------------------

const seenIncidents = new Set<string>();
const grantedIncidents = new Set<string>();
const grantFailed = new Map<string, number>();

function tag(v: any): string {
  if (v === null || v === undefined) return '';
  if (typeof v === 'string') return v;
  if (typeof v === 'object' && 'tag' in v) return String(v.tag);
  return String(v);
}

async function incidentContext(incidentId: string): Promise<{
  zoneId: string; deviceId: string; kind: string; ruleId: string;
  severity: string; description: string;
}> {
  // alert -> first observation gives zone/device/kind; incident row gives
  // title/description/severity. All reads are view-scoped (commander).
  let zoneId = '', deviceId = '', kind = '', ruleId = '', severity = 'medium', description = '';
  try {
    for (const inc of await cmd.db.incidentFeed.iter()) {
      if (inc.id !== incidentId) continue;
      description = String(inc.description ?? '');
      severity = tag(inc.severity) || 'medium';
      break;
    }
    let obsId: bigint | null = null;
    for (const a of await cmd.db.opsAlertFeed.iter()) {
      if (a.incidentId !== incidentId) continue;
      ruleId = String(a.ruleId ?? '');
      obsId = a.observationIds?.[0] ?? null;
      break;
    }
    if (obsId !== null) {
      for (const o of await cmd.db.observationFeed.iter()) {
        if (o.id !== obsId) continue;
        zoneId = String(o.zoneId ?? '');
        deviceId = String(o.deviceId ?? '');
        kind = String(o.kind ?? '');
        break;
      }
    }
  } catch (e) {
    log({ event: 'incident_context_error', incident: incidentId, error: String(e).slice(0, 200) });
  }
  return { zoneId, deviceId, kind, ruleId, severity, description };
}

/** Idempotent responder grant — retried lazily because the commander
 * reducer call is async and may transiently fail. */
async function ensureGrant(incidentId: string): Promise<boolean> {
  if (grantedIncidents.has(incidentId)) return true;
  const fails = grantFailed.get(incidentId) ?? 0;
  if (fails >= 5) return false;
  try {
    await cmd.reducers.grantIncidentAccess({
      incidentId,
      userId: agentIdentity!,
      level: 'responder',
    });
    grantedIncidents.add(incidentId);
    grantFailed.delete(incidentId);
    log({ event: 'agent_granted', incident: incidentId });
    return true;
  } catch (e) {
    grantFailed.set(incidentId, fails + 1);
    log({ event: 'grant_failed', incident: incidentId, attempt: fails + 1, error: String(e).slice(0, 200) });
    return false;
  }
}

async function onNewIncident(incidentId: string): Promise<void> {
  if (seenIncidents.has(incidentId)) return;
  seenIncidents.add(incidentId);
  const ctx = await incidentContext(incidentId);
  // 1) Mirror to the investigator orchestrator — the investigation runs
  //    against the SAME incident id Phantom Command displays.
  const status = await postInvestigationEvent({
    event_id: `incident-${incidentId}`,
    kind: 'incident_created',
    source: 'spacetime',
    incident_id: incidentId,
    device_id: ctx.deviceId,
    zone_id: ctx.zoneId,
    summary: ctx.description || `Auto-correlated incident ${incidentId}`,
    provenance: 'LIVE',
    data: {
      severity: ctx.severity,
      rule_id: ctx.ruleId,
      trigger_kind: ctx.kind,
      confidence: 'suspected',
    },
  });
  log({ event: 'incident_mirrored', incident: incidentId, zone: ctx.zoneId, device: ctx.deviceId, orch: status });
  // 2) Grant the agent responder access so proposeMission/attachEvidence
  //    pass requireIncidentAccess. Commander identity — human-delegated.
  await ensureGrant(incidentId);
}

// ---------------------------------------------------------------------------
// Mission requests -> proposeMission (agent proposes; humans approve)
// ---------------------------------------------------------------------------

const claimedMissions = new Set<string>();        // mission ids bound to a request
const requestMission = new Map<string, string>(); // request_id -> mission_id
const missionRequest = new Map<string, string>(); // mission_id -> request_id
const proposingRequests = new Set<string>();      // proposeMission in flight
const proposingSince = new Map<string, number>(); // rid -> epoch ms
const proposeAttempts = new Map<string, number>();
const ADOPT_TIMEOUT_MS = 90_000;

const LIVE_MISSION_STATES = new Set(['proposed', 'approved', 'dispatched', 'accepted', 'navigating']);

/** True when a non-terminal mission already covers this scope — repeat
 * investigations (e.g. the post-evidence reassessment) must not re-fly
 * the same inspection. */
async function existingMission(incidentId: string, zoneId: string, waypoint: string): Promise<string> {
  try {
    for (const m of await agent.db.missionFeed.iter()) {
      const st = tag(m.state);
      if (LIVE_MISSION_STATES.has(st) || st === 'completed') {
        if (String(m.incidentId) === incidentId && String(m.zoneId) === zoneId
            && String(m.waypoint) === waypoint) {
          return String(m.id);
        }
      }
    }
  } catch { /* view not ready — treat as none */ }
  return '';
}

async function proposeForRequest(req: any): Promise<void> {
  const rid = String(req.request_id);
  const incidentId = String(req.incident_id || '');
  const zoneId = String(req.zone_id || '');
  const waypoint = String(req.waypoint_id || '');
  const deviceId = String(req.device_id || ROVER_DEVICE);
  if (!incidentId || !zoneId || !waypoint) {
    await patchRequest(rid, 'failed', '', 'missing incident/zone/waypoint').catch(() => {});
    return;
  }
  // Grant must land before proposeMission passes requireIncidentAccess.
  if (!(await ensureGrant(incidentId))) return; // stays grant_pending, retried

  const dupe = await existingMission(incidentId, zoneId, waypoint);
  if (dupe) {
    await patchRequest(rid, 'duplicate', dupe, `mission ${dupe} already covers this scope`)
      .catch(() => {});
    log({ event: 'request_duplicate', request: rid, mission: dupe });
    return;
  }

  proposingRequests.add(rid);
  proposingSince.set(rid, Date.now());
  const expiresMicros = (BigInt(Date.now()) + BigInt(MISSION_TTL_S) * 1_000_000n);
  try {
    await agent.reducers.proposeMission({
      incidentId,
      deviceId,
      type: 'inspect_zone',
      waypoint,
      zoneId,
      expiresAtMicros: expiresMicros,
      maxSpeedMps: MISSION_MAX_SPEED,
      justification: `Nemotron investigation ${incidentId}: inspect ${zoneId}@${waypoint} (request ${rid})`,
      traceId: `bridge-${rid}`,
    });
    log({ event: 'mission_proposed', request: rid, incident: incidentId, zone: zoneId, waypoint });
    // 'proposed' state is set by adoptProposedMissions once the mission id
    // is visible in missionFeed; rid stays in proposingRequests until then.
  } catch (e) {
    proposingRequests.delete(rid);
    proposingSince.delete(rid);
    const attempts = (proposeAttempts.get(rid) ?? 0) + 1;
    proposeAttempts.set(rid, attempts);
    const msg = String(e).slice(0, 200);
    if (attempts >= MAX_PROPOSE_ATTEMPTS) {
      await patchRequest(rid, 'failed', '', `proposeMission: ${msg}`).catch(() => {});
      log({ event: 'propose_failed', request: rid, attempts, error: msg });
    } else {
      // Transient (grant lag, reducer race) — back to queued for retry.
      await patchRequest(rid, 'queued', '', `propose retry ${attempts}: ${msg}`).catch(() => {});
      log({ event: 'propose_retry', request: rid, attempts, error: msg });
    }
  }
}

async function adoptProposedMissions(): Promise<void> {
  // proposeMission does not return the id — discover it via missionFeed:
  // newest 'proposed' mission matching a pending request's scope.
  const pending = new Map<string, any>(); // "incident|zone|wp" -> req
  try {
    const r = await api('/internal/mission-requests');
    for (const req of r?.items ?? []) {
      if (req.state === 'queued' || req.state === 'grant_pending'
          || proposingRequests.has(String(req.request_id))) {
        pending.set(`${req.incident_id}|${req.zone_id}|${req.waypoint_id}`, req);
      }
    }
  } catch { return; }
  if (pending.size === 0) return;
  try {
    const missions = [...(await agent.db.missionFeed.iter())];
    for (const m of missions) {
      const mid = String(m.id);
      if (claimedMissions.has(mid)) continue;
      const key = `${m.incidentId}|${m.zoneId}|${m.waypoint}`;
      const req = pending.get(key);
      if (!req || tag(m.state) !== 'proposed') continue;
      claimedMissions.add(mid);
      const rid = String(req.request_id);
      requestMission.set(rid, mid);
      missionRequest.set(mid, rid);
      proposingRequests.delete(rid);
      proposingSince.delete(rid);
      proposeAttempts.delete(rid);
      await patchRequest(rid, 'proposed', mid, 'awaiting commander approval');
      log({ event: 'mission_adopted', request: rid, mission: mid });
    }
  } catch (e) {
    log({ event: 'adopt_error', error: String(e).slice(0, 160) });
  }
  // Adoption timeout: proposeMission succeeded but no matching mission
  // became visible — fail the request rather than wedge it forever.
  const now = Date.now();
  for (const rid of [...proposingRequests]) {
    const since = proposingSince.get(rid) ?? now;
    if (now - since > ADOPT_TIMEOUT_MS) {
      proposingRequests.delete(rid);
      proposingSince.delete(rid);
      await patchRequest(rid, 'failed', '', 'mission adoption timeout — no missionFeed row').catch(() => {});
      log({ event: 'adopt_timeout', request: rid });
    }
  }
}

// ---------------------------------------------------------------------------
// Mission lifecycle tracking + evidence return
// ---------------------------------------------------------------------------

const TERMINAL = new Set(['completed', 'failed', 'expired', 'cancelled']);
const handledTerminal = new Set<string>();
const SHA256_RE = /^[0-9a-f]{64}$/;

function isoToMicros(iso: string): bigint {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? 0n : BigInt(ms) * 1000n;
}

function findInspectionMeta(missionId: string): any | null {
  if (!EVIDENCE_DIR || !existsSync(EVIDENCE_DIR)) return null;
  try {
    for (const zone of readdirSync(EVIDENCE_DIR)) {
      const zdir = join(EVIDENCE_DIR, zone);
      let files: string[] = [];
      try { files = readdirSync(zdir); } catch { continue; }
      for (const f of files) {
        if (!f.endsWith('.meta.json')) continue;
        try {
          const meta = JSON.parse(readFileSync(join(zdir, f), 'utf8'));
          if (meta.mission_id === missionId) return meta;
        } catch { /* skip unreadable */ }
      }
    }
  } catch { /* dir vanished */ }
  return null;
}

async function onMissionTerminal(m: any): Promise<void> {
  const mid = String(m.id);
  if (handledTerminal.has(mid)) return;
  handledTerminal.add(mid);
  const rid = missionRequest.get(mid) ?? '';
  const state = tag(m.state);
  const reqState = state === 'completed' ? 'completed' : 'failed';
  if (rid) await patchRequest(rid, reqState, mid, `mission ${state}`).catch(() => {});

  // Attach the inspection report to the incident (responder access) so
  // Phantom Command's evidenceFeed shows it, then notify the orchestrator
  // so Nemotron re-assesses with the real evidence in scope.
  const incidentId = String(m.incidentId ?? '');
  const meta = findInspectionMeta(mid);
  if (meta && incidentId && grantedIncidents.has(incidentId)) {
    const sha = String(meta.sha256 ?? '').toLowerCase();
    if (SHA256_RE.test(sha)) {
      let observed = isoToMicros(String(meta.observed_at ?? meta.received_at ?? ''));
      const nowMicros = BigInt(Date.now()) * 1000n;
      // Reducer rejects observed_at > now+5min; absent/garbage -> now.
      if (observed <= 0n || observed > nowMicros + 5n * 60n * 1_000_000n) {
        observed = nowMicros;
      }
      try {
        await agent.reducers.attachEvidence({
          incidentId,
          source: `rover/${ROVER_DEVICE}/network_inspection`,
          observedAtMicros: observed,
          storageRef: String(meta.storage_ref ?? meta.path ?? '').slice(0, 512),
          sha256: sha,
          trustTier: 'device_asserted',
          traceId: `bridge-evidence-${mid}`,
        });
        log({ event: 'evidence_attached', mission: mid, incident: incidentId, artifact: meta.artifact_id });
      } catch (e) {
        log({ event: 'attach_failed', mission: mid, error: String(e).slice(0, 200) });
      }
    } else {
      log({ event: 'attach_skipped_bad_sha', mission: mid });
    }
  }
  try {
    const orch = await postInvestigationEvent({
      event_id: `evidence-${mid}`,
      kind: 'inspection_evidence',
      source: 'rover',
      incident_id: incidentId,
      device_id: ROVER_DEVICE,
      zone_id: String(m.zoneId ?? ''),
      summary: `Rover inspection ${mid} ${state}` +
        (meta ? ` — ${meta.target_device_id ?? ''} status=${meta.status ?? '?'}` : ''),
      provenance: meta?.synthetic ? 'DEMO' : 'LIVE',
      data: {
        mission_id: mid,
        mission_state: state,
        artifact_id: meta?.artifact_id ?? '',
        target_device_id: meta?.target_device_id ?? '',
        inspection_status: meta?.status ?? '',
        sha256: meta?.sha256 ?? '',
      },
    });
    log({ event: 'evidence_event', mission: mid, incident: incidentId, orch });
  } catch (e) {
    log({ event: 'evidence_event_failed', mission: mid, error: String(e).slice(0, 200) });
  }
}

async function trackMissions(): Promise<void> {
  try {
    const missions = [...(await cmd.db.missionFeed.iter())];
    for (const m of missions) {
      const mid = String(m.id);
      const st = tag(m.state);
      const rid = missionRequest.get(mid);
      if (rid && !TERMINAL.has(st)) {
        const mapped = st === 'approved' ? 'approved'
          : st === 'dispatched' ? 'dispatched'
          : st === 'accepted' || st === 'navigating' ? 'executing' : '';
        if (mapped) await patchRequest(rid, mapped, mid).catch(() => {});
      }
      if (TERMINAL.has(st)) await onMissionTerminal(m);
    }
  } catch (e) {
    log({ event: 'track_error', error: String(e).slice(0, 160) });
  }
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

async function scanIncidents(): Promise<void> {
  try {
    for (const inc of await cmd.db.incidentFeed.iter()) {
      const id = String(inc.id ?? '');
      if (id) await onNewIncident(id);
    }
  } catch (e) {
    log({ event: 'incident_scan_error', error: String(e).slice(0, 160) });
  }
}

async function scanRequests(): Promise<void> {
  let items: any[] = [];
  try {
    const r = await api('/internal/mission-requests');
    items = r?.items ?? [];
  } catch (e) {
    log({ event: 'requests_error', error: String(e).slice(0, 160) });
    return;
  }
  for (const req of items) {
    const rid = String(req.request_id);
    const st = String(req.state);
    if (proposingRequests.has(rid)) continue; // propose in flight
    if ((st === 'queued' || st === 'grant_pending')
        && String(req.type) === 'inspect_zone') {
      if (st === 'queued') {
        // Mark grant-pending so concurrent readers see intent; proposeForRequest
        // flips back to 'queued' on transient failure or 'proposed' on adopt.
        await patchRequest(rid, 'grant_pending', '', 'waiting for incident grant').catch(() => {});
      }
      await proposeForRequest(req);
    } else if (st === 'queued') {
      await patchRequest(rid, 'failed', '', `unsupported request type ${req.type}`).catch(() => {});
    }
  }
}

log({ event: 'bridge_ready', poll_ms: POLL_MS, rover: ROVER_DEVICE });

// Baseline: incidents already in the feed are history — never replay
// investigations/grants for them. Only incidents created after this
// point are mirrored to the orchestrator.
try {
  for (const inc of await cmd.db.incidentFeed.iter()) {
    const id = String(inc.id ?? '');
    if (id) seenIncidents.add(id);
  }
  log({ event: 'baseline_incidents', count: seenIncidents.size });
} catch (e) {
  log({ event: 'baseline_error', error: String(e).slice(0, 160) });
}

for (;;) {
  await scanIncidents();
  await scanRequests();
  await adoptProposedMissions();
  await trackMissions();
  await sleep(POLL_MS);
}
