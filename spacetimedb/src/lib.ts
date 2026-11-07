import { SenderError, Range } from 'spacetimedb/server';
import type { ReadonlyDbView, ReducerCtx, InferSchema } from 'spacetimedb/server';
import type { Identity } from 'spacetimedb';
import type spacetimedb from './schema';
import type {
  ChatKindValue,
  ConfidenceValue,
  IncidentAccessLevelValue,
  IncidentStatusValue,
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
  'contact_open',
  'contact_closed',
  'motion',
  'photo_captured',
  'mission_status',
  'rf_frame_meta',
  'tag_seen',
  'temperature',
  'door_state',
  'signal_strength',
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

