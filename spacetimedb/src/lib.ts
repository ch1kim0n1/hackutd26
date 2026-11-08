import { SenderError, Range } from 'spacetimedb/server';
import type { ReadonlyDbView, ReducerCtx, InferSchema } from 'spacetimedb/server';
import type { Identity } from 'spacetimedb';
import type spacetimedb from './schema';
import type {
  AlertStateValue,
  ChatKindValue,
  ConfidenceValue,
  IncidentAccessLevelValue,
  IncidentStatusValue,
  MissionStateValue,
  SeverityValue,
} from './schema';
import { Timestamp } from 'spacetimedb';

export type Ctx = ReducerCtx<InferSchema<typeof spacetimedb>>;

/** Minimal read context shared by reducers (Ctx) and views (ViewCtx). */
export type ReadCtx = {
  sender: Identity;
  db: ReadonlyDbView<InferSchema<typeof spacetimedb>>;
};

// ---------------------------------------------------------------------------
// Constants (bounds enforced by reducers; see docs/04-DATA-AND-INTERFACES.md)
// ---------------------------------------------------------------------------

export const MAX_DATA_JSON_BYTES = 8192;
export const MAX_CHAT_BODY_CHARS = 4000;
export const MAX_DESCRIPTION_CHARS = 8000;

// Incident lifecycle transition table (docs/04 + docs/06 R03).
export const INCIDENT_TRANSITIONS: Record<string, readonly string[]> = {
  new: ['triage', 'dismissed'],
  triage: ['investigating', 'dismissed', 'new'],
  investigating: ['containment_pending', 'resolved', 'dismissed'],
  containment_pending: ['contained', 'investigating'],
  contained: ['recovery', 'resolved'],
  recovery: ['resolved', 'investigating'],
  resolved: ['closed', 'investigating'],
  closed: [],
  dismissed: [],
};

/**
 * Internal incident row constructor — shared by the public reducer and by the
 * deterministic correlation engine running inside ingest transactions.
 * Creates the incident, grants commander access, writes audit.
 */
export function insertIncident(
  ctx: Ctx,
  opts: {
    title: string;
    description: string;
    severity: SeverityValue['tag'];
    confidence: ConfidenceValue['tag'];
    status: IncidentStatusValue['tag'];
    commanderId: Ctx['sender'];
    traceId: string;
    operation?: string;
  }
): { id: string } {
  const id = newId('inc', ctx);
  const title = boundedString(opts.title, 256, 'title');
  const description = boundedString(opts.description, MAX_DESCRIPTION_CHARS, 'description');
  ctx.db.incidents.insert({
    id,
    title,
    description,
    severity: tagValue<SeverityValue>(opts.severity),
    confidence: tagValue<ConfidenceValue>(opts.confidence),
    status: tagValue<IncidentStatusValue>(opts.status),
    commanderId: opts.commanderId,
    createdAt: ctx.timestamp,
    updatedAt: ctx.timestamp,
    version: 1n,
    traceId: opts.traceId,
  });
  grantAccess(ctx, id, opts.commanderId, 'commander', opts.commanderId);
  audit(ctx, {
    actor: opts.commanderId,
    operation: opts.operation ?? 'incident.create',
    entity: `incident:${id}`,
    incidentId: id,
    after: { id, title, severity: opts.severity, status: opts.status },
    traceId: opts.traceId,
  });
  return { id };
}
export const MAX_REASON_CHARS = 2000;
export const MAX_NOTE_CHARS = 2000;
export const MAX_PAYLOAD_JSON_BYTES = 16384;

export const OBS_MAX_AGE_MICROS = 24n * 60n * 60n * 1_000_000n; // 24h
export const OBS_MAX_FUTURE_SKEW_MICROS = 5n * 60n * 1_000_000n; // +5min
export const MISSION_MAX_TTL_MICROS = 15n * 60n * 1_000_000n; // 15min
export const APPROVAL_DEFAULT_TTL_MICROS = 15n * 60n * 1_000_000n;
export const APPROVAL_MAX_TTL_MICROS = 60n * 60n * 1_000_000n;
export const OUTBOX_MAX_ATTEMPTS = 8;
export const OUTBOX_CLAIM_TTL_MICROS = 2n * 60n * 1_000_000n; // 2min

export const OBSERVATION_KINDS = new Set([
  'wifi_ap_seen',
  'wifi_probe',
  'ble_beacon',
  'ble_beacon_seen',
  'contact_open',
  'contact_closed',
  'cabinet_contact_open',
  'cabinet_contact_closed',
  'device_health',
  'device_offline',
  'motion',
  'photo_captured',
  'mission_status',
  'rf_frame_meta',
  'tag_seen',
  'temperature',
  'door_state',
  'signal_strength',
  // Data-center node telemetry (apps/datacenter; same envelope contract
  // physical Pi monitoring agents must honor — docs/13 section 5).
  'service_inventory',
  'network_flow',
  'resource_metric',
  'config_drift',
]);

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

/** Deterministic non-cryptographic fingerprint (FNV-1a 64-bit) over canonical JSON. */
export function fingerprintOf(canonical: string): string {
  let h = 0xcbf29ce484222325n;
  const prime = 0x100000001b3n;
  const mask = 0xffffffffffffffffn;
  for (let i = 0; i < canonical.length; i++) {
    h ^= BigInt(canonical.charCodeAt(i));
    h = (h * prime) & mask;
  }
  return h.toString(16).padStart(16, '0');
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(sortKeys(value));
}

function sortKeys(value: unknown): unknown {
  if (typeof value === 'bigint') return value.toString();
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === 'object') {
    const v = value as Record<string, unknown>;
    // SpacetimeDB runtime types (Identity, Uuid, Timestamp, ...) are class
    // instances, not plain objects — serialize them deterministically instead
    // of recursing into internals (which contain raw bigints).
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null) {
      if (typeof v.toHexString === 'function') {
        return (v.toHexString as () => string)();
      }
      if (typeof v.microsSinceUnixEpoch === 'bigint') {
        return { micros: v.microsSinceUnixEpoch.toString() };
      }
      if (typeof v.toString === 'function' && v.toString !== Object.prototype.toString) {
        return v.toString();
      }
      return String(value);
    }
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(v).sort()) {
      out[k] = sortKeys(v[k]);
    }
    return out;
  }
  return value;
}

export function newId(prefix: string, ctx: Ctx): string {
  return `${prefix}-${ctx.newUuidV4().toString()}`;
}

export function microsToTimestamp(micros: bigint): Timestamp {
  return new Timestamp(micros);
}

/** Build a SATS simple-enum value `{ tag }` for a validated case string. */
export function tagValue<T extends { tag: string }>(tag: string): T {
  return { tag } as T;
}

/** Validate a raw string against an enum case list; returns the case string. */
export function requireEnum(value: string, cases: readonly string[], field: string): string {
  const v = boundedString(value, 64, field);
  if (!cases.includes(v)) {
    throw new SenderError(`invalid ${field}: ${v}`);
  }
  return v;
}

export function nowMicros(ctx: Ctx): bigint {
  return ctx.timestamp.microsSinceUnixEpoch;
}

export function boundedString(value: string, maxChars: number, field: string): string {
  const trimmed = value.trim();
  if (trimmed.length === 0) throw new SenderError(`${field} must not be empty`);
  if (trimmed.length > maxChars) {
    throw new SenderError(`${field} exceeds ${maxChars} characters`);
  }
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f-\u009f]/.test(trimmed)) {
    throw new SenderError(`${field} contains control characters`);
  }
  return trimmed;
}

export function jsonBounded(value: string, maxBytes: number, field: string): string {
  const trimmed = value.trim();
  if (trimmed.length === 0) throw new SenderError(`${field} must not be empty`);
  if (trimmed.length > maxBytes) {
    throw new SenderError(`${field} exceeds ${maxBytes} bytes`);
  }
  return trimmed;
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export interface AuditEntry {
  actor: Ctx['sender'];
  operation: string;
  entity: string;
  incidentId: string;
  before?: unknown;
  after?: unknown;
  detail?: unknown;
  traceId: string;
}

export function audit(ctx: Ctx, entry: AuditEntry): void {
  const beforeJson = entry.before === undefined ? '' : canonicalJson(entry.before);
  const afterJson = entry.after === undefined ? '' : canonicalJson(entry.after);
  const detailJson = entry.detail === undefined ? '' : canonicalJson(entry.detail);
  ctx.db.auditEvents.insert({
    id: 0n,
    actor: entry.actor,
    operation: entry.operation,
    entity: entry.entity,
    incidentId: entry.incidentId,
    beforeHash: beforeJson === '' ? '' : fingerprintOf(beforeJson),
    afterHash: afterJson === '' ? '' : fingerprintOf(afterJson),
    detailJson,
    at: ctx.timestamp,
    traceId: entry.traceId,
  });
}

// ---------------------------------------------------------------------------
// Authorization
// ---------------------------------------------------------------------------

export type Principal = {
  userId: Ctx['sender'];
  role: string;
  incidentScope: string[];
  revoked: boolean;
};

export function principalOf(ctx: ReadCtx): Principal | null {
  const row = ctx.db.usersAndRoles.userId.find(ctx.sender);
  if (!row || row.revoked) return null;
  return { userId: row.userId, role: row.role.tag, incidentScope: row.incidentScope, revoked: row.revoked };
}

export function hasRole(ctx: ReadCtx, ...roles: string[]): boolean {
  const p = principalOf(ctx);
  return p !== null && roles.includes(p.role);
}

export function requireRole(ctx: ReadCtx, ...roles: string[]): void {
  if (!hasRole(ctx, ...roles)) {
    throw new SenderError(`forbidden: requires one of roles [${roles.join(', ')}]`);
  }
}

const ACCESS_RANK: Record<string, number> = {
  viewer: 1,
  responder: 2,
  commander: 3,
  admin: 4,
};

export function accessRank(level: string): number {
  return ACCESS_RANK[level] ?? 0;
}

/**
 * Resolve caller's effective access level on an incident.
 * Admin role => 4 (all incidents). Otherwise incident.commanderId match => 3,
 * else incident_access grant row. No access => 0.
 */
export function incidentAccessLevel(ctx: ReadCtx, incidentId: string): number {
  const p = principalOf(ctx);
  if (p === null) return 0;
  if (p.role === 'admin') return ACCESS_RANK.admin;
  const incident = ctx.db.incidents.id.find(incidentId);
  if (incident !== null && incident.commanderId.isEqual(ctx.sender)) {
    return ACCESS_RANK.commander;
  }
  for (const grant of ctx.db.incidentAccess.incidentId.filter(incidentId)) {
    if (grant.userId.isEqual(ctx.sender)) {
      return accessRank(grant.level.tag);
    }
  }
  return 0;
}

export function requireIncidentAccess(ctx: ReadCtx, incidentId: string, minLevel: string): void {
  const level = incidentAccessLevel(ctx, incidentId);
  if (level < accessRank(minLevel)) {
    throw new SenderError(
      `forbidden: incident ${incidentId} requires ${minLevel} access (have ${level})`
    );
  }
}

/** Post a system-kind chat message on behalf of the current reducer caller. */
export function postSystemChat(
  ctx: Ctx,
  incidentId: string,
  body: string,
  refId: string
): void {
  const clean = boundedString(body, MAX_CHAT_BODY_CHARS, 'body');
  const p = principalOf(ctx);
  ctx.db.chatMessages.insert({
    id: 0n,
    incidentId,
    sender: ctx.sender,
    senderRole: p?.role ?? 'system',
    kind: { tag: 'system' } as ChatKindValue,
    body: clean,
    refId: boundedString(refId, 128, 'ref_id'),
    createdAt: ctx.timestamp,
    clientNonce: `sys-${ctx.newUuidV4().toString()}`,
    traceId: `sys-${ctx.newUuidV4().toString()}`,
  });
}

/** Insert or upgrade an incident_access grant (never downgrades). */
export function grantAccess(
  ctx: Ctx,
  incidentId: string,
  userId: Ctx['sender'],
  level: 'viewer' | 'responder' | 'commander',
  grantedBy: Ctx['sender']
): void {
  const lvl = { tag: level } as IncidentAccessLevelValue;
  for (const g of ctx.db.incidentAccess.incidentId.filter(incidentId)) {
    if (g.userId.isEqual(userId)) {
      if (accessRank(level) > accessRank(g.level.tag)) {
        ctx.db.incidentAccess.id.delete(g.id);
        ctx.db.incidentAccess.insert({
          id: 0n,
          incidentId,
          userId,
          level: lvl,
          grantedBy,
          grantedAt: ctx.timestamp,
        });
      }
      return;
    }
  }
  ctx.db.incidentAccess.insert({
    id: 0n,
    incidentId,
    userId,
    level: lvl,
    grantedBy,
    grantedAt: ctx.timestamp,
  });
}

type IncidentRow = NonNullable<ReturnType<ReadonlyDbView<InferSchema<typeof spacetimedb>>['incidents']['id']['find']>>;

/** Incident rows visible to the caller (admin => all; else grants + command). */
export function visibleIncidents(ctx: ReadCtx): IncidentRow[] {
  const p = principalOf(ctx);
  if (p === null) return [];
  const out = new Map<string, IncidentRow>();
  if (p.role === 'admin') {
    for (const inc of ctx.db.incidents.createdAt.filter(new Range<Timestamp>())) {
      out.set(inc.id, inc);
    }
    return [...out.values()];
  }
  for (const g of ctx.db.incidentAccess.userId.filter(ctx.sender)) {
    const row = ctx.db.incidents.id.find(g.incidentId);
    if (row !== null) out.set(row.id, row);
  }
  for (const inc of ctx.db.incidents.commanderId.filter(ctx.sender)) {
    out.set(inc.id, inc);
  }
  return [...out.values()];
}

/** All incident ids the caller can see (admin => every incident). */
export function visibleIncidentIds(ctx: ReadCtx): string[] {
  return visibleIncidents(ctx).map((i) => i.id);
}


// ---------------------------------------------------------------------------
// Deterministic observation -> alert -> incident correlation (issue #18)
// ---------------------------------------------------------------------------

const CORRELATION_BUCKET_MICROS = 300_000_000n; // 5-minute dedupe window

interface CorrelationRule {
  ruleId: string;
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  incident: boolean;
  title: string;
}

// Deterministic rules: same observation kind always maps to the same
// alert/incident template. Wi-Fi-only anomalies stay alert-tier — docs/08
// forbids claiming exposure from RF anomalies alone.
const CORRELATION_RULES: Record<string, CorrelationRule> = {
  contact_open: {
    ruleId: 'perimeter.contact_open',
    severity: 'high',
    incident: true,
    title: 'Physical perimeter contact opened',
  },
  cabinet_contact_open: {
    ruleId: 'perimeter.cabinet_contact_open',
    severity: 'high',
    incident: true,
    title: 'Cabinet contact opened',
  },
  device_offline: {
    ruleId: 'device.offline',
    severity: 'medium',
    incident: false,
    title: 'Device reported offline',
  },
  ble_beacon_seen: {
    ruleId: 'rf.ble_beacon_seen',
    severity: 'low',
    incident: false,
    title: 'BLE beacon observed',
  },
  door_state: {
    ruleId: 'door.state_change',
    severity: 'medium',
    incident: false,
    title: 'Door state change',
  },
  motion: {
    ruleId: 'physical.motion',
    severity: 'low',
    incident: false,
    title: 'Motion detected',
  },
  wifi_ap_seen: {
    ruleId: 'rf.ap_seen',
    severity: 'low',
    incident: false,
    title: 'Wi-Fi AP observed',
  },
};

/** First non-revoked commander in the directory (deterministic: createdAt). */
function pickOncallCommander(ctx: Ctx): Ctx['sender'] | null {
  for (const u of ctx.db.usersAndRoles.createdAt.filter(new Range<Timestamp>())) {
    if (!u.revoked && u.role.tag === 'commander') return u.userId;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Data-center node telemetry rules (apps/datacenter virtual Pi fleet).
// These are DATA-AWARE: device_health correlates on data.status so plain
// 'ok' heartbeats never alert; the other kinds fire on objective payload
// fields. Physical Pi agents use the identical envelope + data shapes.
// ---------------------------------------------------------------------------

const DC_HEALTH_RULES: Record<string, CorrelationRule> = {
  fault: {
    ruleId: 'node.health_fault',
    severity: 'high',
    incident: true,
    title: 'Node reported fault',
  },
  stale: {
    ruleId: 'node.health_stale',
    severity: 'medium',
    incident: true,
    title: 'Node heartbeat lost (stale)',
  },
  degraded: {
    ruleId: 'node.health_degraded',
    severity: 'low',
    incident: false,
    title: 'Node degraded',
  },
};

const DC_SERVICE_RULE: CorrelationRule = {
  ruleId: 'dc.unexpected_service',
  severity: 'high',
  incident: true,
  title: 'Unexpected service listener detected',
};

const DC_DRIFT_RULE: CorrelationRule = {
  ruleId: 'dc.config_drift',
  severity: 'medium',
  incident: true,
  title: 'Configuration drift detected',
};

const DC_FLOW_RULE: CorrelationRule = {
  ruleId: 'dc.suspicious_flow',
  severity: 'high',
  incident: true,
  title: 'Suspicious network flow pattern',
};

// Deterministic flow heuristics — objective thresholds only, no labels.
const FLOW_SCAN_PORT_THRESHOLD = 8;                    // distinct dst ports
const FLOW_BULK_BYTES_THRESHOLD = 64n * 1024n * 1024n;  // 64 MiB
const FLOW_KNOWN_BAD_PORTS = new Set([4444, 5555, 6667, 12345, 31337]);

function parseObsData(dataJson: string): Record<string, unknown> {
  try {
    const d: unknown = JSON.parse(dataJson);
    if (d !== null && typeof d === 'object' && !Array.isArray(d)) {
      return d as Record<string, unknown>;
    }
  } catch {
    /* fall through */
  }
  return {};
}

function numField(d: Record<string, unknown>, key: string): number | null {
  const v = d[key];
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** Objective suspicious-flow check: scan breadth, bulk transfer, or a
 *  known-bad destination port. Benign lab flows never match. */
function flowIsSuspicious(d: Record<string, unknown>): boolean {
  const distinct = numField(d, 'distinct_dst_ports');
  if (distinct !== null && distinct >= FLOW_SCAN_PORT_THRESHOLD) return true;
  const bytes = numField(d, 'bytes');
  if (bytes !== null && BigInt(Math.trunc(bytes)) >= FLOW_BULK_BYTES_THRESHOLD) {
    return true;
  }
  const port = numField(d, 'dst_port');
  if (port !== null && FLOW_KNOWN_BAD_PORTS.has(Math.trunc(port))) return true;
  return false;
}

/** Map an observation to its correlation rule, or undefined for
 *  non-actionable telemetry (heartbeats, metrics, benign flows). */
function ruleForObservation(
  kind: string,
  dataJson: string
): CorrelationRule | undefined {
  const d = parseObsData(dataJson);
  switch (kind) {
    case 'device_health': {
      const status = typeof d.status === 'string' ? d.status : '';
      return DC_HEALTH_RULES[status];
    }
    case 'service_inventory': {
      const unexp = Array.isArray(d.unexpected) ? d.unexpected : [];
      return unexp.length > 0 ? DC_SERVICE_RULE : undefined;
    }
    case 'config_drift':
      return d.resolved === true ? undefined : DC_DRIFT_RULE;
    case 'network_flow':
      return flowIsSuspicious(d) ? DC_FLOW_RULE : undefined;
    default:
      return CORRELATION_RULES[kind];
  }
}

/** Recovery signals clear open auto-alerts for the reporting device —
 *  they never create alerts/incidents themselves. */
function recoveryRuleIdsFor(kind: string, dataJson: string): string[] | null {
  const d = parseObsData(dataJson);
  if (kind === 'device_health' && d.status === 'ok' && d.recovered === true) {
    return Object.values(DC_HEALTH_RULES).map((r) => r.ruleId);
  }
  if (kind === 'config_drift' && d.resolved === true) {
    return [DC_DRIFT_RULE.ruleId];
  }
  if (kind === 'service_inventory'
      && Array.isArray(d.unexpected) && d.unexpected.length === 0) {
    return [DC_SERVICE_RULE.ruleId];
  }
  return null;
}

/** Resolve open auto-alerts raised for `deviceId` under `ruleIds`, and
 *  move linked incidents to `recovery` when the lifecycle allows it. */
function handleTelemetryRecovery(
  ctx: Ctx,
  obs: { deviceId: string; kind: string; eventId: string; traceId: string },
  ruleIds: string[]
): void {
  const wanted = new Set(ruleIds);
  const incidentIds = new Set<string>();
  let resolved = 0;
  for (const alert of ctx.db.alerts.createdAt.filter(new Range<Timestamp>())) {
    if (!wanted.has(alert.ruleId)) continue;
    if (alert.state.tag !== 'open' && alert.state.tag !== 'acknowledged') {
      continue;
    }
    // alerts don't carry deviceId — resolve via their first observation
    const firstObsId = alert.observationIds.length > 0
      ? alert.observationIds[0]
      : null;
    const firstObs = firstObsId === null
      ? null
      : ctx.db.observations.id.find(firstObsId);
    if (firstObs === null || firstObs.deviceId !== obs.deviceId) continue;
    ctx.db.alerts.id.update({
      ...alert,
      state: tagValue<AlertStateValue>('resolved'),
    });
    resolved++;
    if (alert.incidentId.length > 0) incidentIds.add(alert.incidentId);
  }
  for (const incidentId of incidentIds) {
    const inc = ctx.db.incidents.id.find(incidentId);
    if (inc === null) continue;
    const canRecover = (INCIDENT_TRANSITIONS[inc.status.tag] ?? []).includes('recovery');
    if (canRecover) {
      ctx.db.incidents.id.update({
        ...inc,
        status: tagValue<IncidentStatusValue>('recovery'),
        updatedAt: ctx.timestamp,
        version: inc.version + 1n,
      });
    }
    postSystemChat(
      ctx,
      incidentId,
      `Telemetry recovery signal (${obs.kind}) from ${obs.deviceId} ` +
        `(${obs.eventId}); ${resolved} auto-alert(s) resolved` +
        (canRecover ? ', incident moved to recovery.' : '.'),
      obs.eventId
    );
    audit(ctx, {
      actor: ctx.sender,
      operation: 'correlate.recovery',
      entity: `incident:${incidentId}`,
      incidentId,
      after: { deviceId: obs.deviceId, kind: obs.kind, eventId: obs.eventId },
      traceId: obs.traceId,
    });
  }
  if (resolved > 0 || incidentIds.size > 0) {
    audit(ctx, {
      actor: ctx.sender,
      operation: 'correlate.recovery_scan',
      entity: `device:${obs.deviceId}`,
      incidentId: '',
      after: { deviceId: obs.deviceId, kind: obs.kind, alertsResolved: resolved },
      traceId: obs.traceId,
    });
  }
}

/**
 * Runs inside the ingest transaction: inserts an alert for every matched
 * observation kind, and for incident-tier rules creates exactly one incident
 * per (rule, device, zone, 5-minute bucket) via correlation_dedupe. Replays
 * of the same event or a second event in the same bucket are no-ops.
 * Data-center kinds are data-aware (see ruleForObservation); recovery
 * signals resolve matching open alerts instead of alerting.
 */
export function correlateObservation(
  ctx: Ctx,
  obs: {
    id: bigint;
    eventId: string;
    deviceId: string;
    kind: string;
    observedAt: Timestamp;
    zoneId: string;
    dataJson: string;
    traceId: string;
  }
): void {
  const recoveryRules = recoveryRuleIdsFor(obs.kind, obs.dataJson);
  if (recoveryRules !== null) {
    handleTelemetryRecovery(ctx, obs, recoveryRules);
    return;
  }
  const rule = ruleForObservation(obs.kind, obs.dataJson);
  if (rule === undefined) return;

  const bucket = obs.observedAt.microsSinceUnixEpoch / CORRELATION_BUCKET_MICROS;
  const key = `${rule.ruleId}:${obs.deviceId}:${obs.zoneId}:${bucket}`;
  if (ctx.db.correlationDedupe.key.find(key) !== null) return;

  const alert = ctx.db.alerts.insert({
    id: 0n,
    ruleId: rule.ruleId,
    observationIds: [obs.id],
    severity: tagValue<SeverityValue>(rule.severity),
    state: tagValue<AlertStateValue>('open'),
    incidentId: '',
    title: `${rule.title} — ${obs.deviceId}@${obs.zoneId}`,
    createdAt: ctx.timestamp,
  });

  let incidentId = '';
  if (rule.incident) {
    const commanderId = pickOncallCommander(ctx);
    if (commanderId !== null) {
      const inc = insertIncident(ctx, {
        title: `${rule.title} — ${obs.zoneId}`,
        description: `Auto-correlated from ${obs.kind} observation ${obs.eventId} (device ${obs.deviceId}, zone ${obs.zoneId}). Confidence: suspected — awaiting human triage.`,
        severity: rule.severity,
        confidence: 'suspected',
        status: 'new',
        commanderId,
        traceId: obs.traceId,
        operation: 'incident.auto_correlate',
      });
      incidentId = inc.id;
      ctx.db.alerts.id.update({ ...alert, incidentId });
      postSystemChat(
        ctx,
        incidentId,
        `Auto-incident created from observation ${obs.eventId} (${obs.kind} on ${obs.deviceId}).`,
        obs.eventId
      );
    }
  }

  ctx.db.correlationDedupe.insert({
    key,
    alertId: alert.id,
    incidentId,
    createdAt: ctx.timestamp,
  });

  audit(ctx, {
    actor: ctx.sender,
    operation: 'correlate.observation',
    entity: `alert:${alert.id}`,
    incidentId,
    after: {
      ruleId: rule.ruleId,
      kind: obs.kind,
      deviceId: obs.deviceId,
      zoneId: obs.zoneId,
      bucket: bucket.toString(),
    },
    traceId: obs.traceId,
  });
}

// ---------------------------------------------------------------------------
// mission_status observations -> mission state machine (rover telemetry path)
// ---------------------------------------------------------------------------

const MISSION_STATUS_DEVICE_STATES = new Set([
  'accepted',
  'navigating',
  'completed',
  'failed',
]);
const MISSION_STATUS_RANK: Record<string, number> = {
  proposed: -1,
  approved: 0,
  dispatched: 1,
  accepted: 2,
  navigating: 3,
};
const MISSION_TERMINAL = new Set(['completed', 'failed', 'expired', 'cancelled']);

/**
 * Rover/device mission telemetry arrives as `mission_status` observations
 * through the gateway (the rover cannot hold a device principal). Mirrors
 * the recordMissionResult transition legality inside the ingest transaction
 * so the mission projection tracks real device progress. Non-throwing:
 * an unmatched/illegal status is skipped — the observation row stands on
 * its own as evidence; out-of-order telemetry must not fail ingest.
 */
export function applyMissionStatus(
  ctx: Ctx,
  deviceId: string,
  dataJson: string,
  eventId: string,
  traceId: string
): void {
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(dataJson) as Record<string, unknown>;
  } catch {
    return;
  }
  const missionId = typeof data.mission_id === 'string' ? data.mission_id : '';
  const state = typeof data.state === 'string' ? data.state : '';
  if (missionId === '' || !MISSION_STATUS_DEVICE_STATES.has(state)) return;

  const mission = ctx.db.missions.id.find(missionId);
  if (mission === null || mission.deviceId !== deviceId) return;
  const from = mission.state.tag;
  if (MISSION_TERMINAL.has(from)) return; // terminal replay: no-op
  const fromRank = MISSION_STATUS_RANK[from] ?? -2;
  const ok =
    (state === 'accepted' && (from === 'dispatched' || from === 'accepted')) ||
    (state === 'navigating' &&
      (from === 'dispatched' || from === 'accepted' || from === 'navigating')) ||
    ((state === 'completed' || state === 'failed') && fromRank >= 1);
  if (!ok) return;

  const reason = typeof data.reason === 'string' ? data.reason.slice(0, 256) : '';
  ctx.db.missions.id.update({
    ...mission,
    state: tagValue<MissionStateValue>(state),
    resultJson: canonicalJson({ source: 'mission_status', eventId, reason }),
    updatedAt: ctx.timestamp,
    version: mission.version + 1n,
  });
  audit(ctx, {
    actor: ctx.sender,
    operation: 'mission.status_observed',
    entity: `mission:${missionId}`,
    incidentId: mission.incidentId,
    after: { from, to: state, eventId, provenance: 'device_relayed' },
    traceId,
  });
}
