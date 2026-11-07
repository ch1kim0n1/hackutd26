import { Timestamp } from 'spacetimedb';
import { Range, t } from 'spacetimedb/server';
import spacetimedb, {
  actions,
  alerts,
  approvals,
  assets,
  auditEvents,
  chatMessages,
  devicePrincipals,
  devices,
  evidence,
  health,
  incidents,
  incidentAccess,
  missions,
  observations,
  outbox,
  rfFrames,
  scopeEntries,
  usersAndRoles,
  zones,
} from './schema';
import {
  accessRank,
  incidentAccessLevel,
  principalOf,
  tagValue,
  visibleIncidents,
  type ReadCtx,
} from './lib';
import type { MissionStateValue, OutboxStateValue } from './schema';

const HUMAN_ROLES = new Set(['admin', 'commander', 'responder', 'observer', 'agent']);

function canReadOps(ctx: ReadCtx): boolean {
  const p = principalOf(ctx);
  return p !== null && !p.revoked && HUMAN_ROLES.has(p.role);
}

function allViaIndex<T>(iter: () => IteratorObject<T, undefined>): T[] {
  return [...iter()];
}

// ---------------------------------------------------------------------------
// Identity / access projections
// ---------------------------------------------------------------------------

export const myAccess = spacetimedb.view(
  { name: 'my_access', public: true },
  t.option(usersAndRoles.rowType),
  (ctx) => ctx.db.usersAndRoles.userId.find(ctx.sender) ?? undefined
);

export const myDevicePrincipal = spacetimedb.view(
  { name: 'my_device_principal', public: true },
  t.option(devicePrincipals.rowType),
  (ctx) => ctx.db.devicePrincipals.identity.find(ctx.sender) ?? undefined
);

// ---------------------------------------------------------------------------
// Incident-scoped feeds — each returns only rows for incidents the caller can
// access. This is the "cross-incident subscriptions denied" control: a client
// subscribed to incidentFeed/chatFeed/etc. never receives another team's rows.
// ---------------------------------------------------------------------------

export const incidentFeed = spacetimedb.view(
  { name: 'incident_feed', public: true },
  t.array(incidents.rowType),
  (ctx) => visibleIncidents(ctx)
);

export const accessFeed = spacetimedb.view(
  { name: 'incident_access_feed', public: true },
  t.array(incidentAccess.rowType),
  (ctx) => {
    const out = [];
    for (const inc of visibleIncidents(ctx)) {
      for (const g of ctx.db.incidentAccess.incidentId.filter(inc.id)) {
        out.push(g);
      }
    }
    return out;
  }
);

function rowsForIncidents<TRow>(
  ctx: ReadCtx,
  filter: (incidentId: string) => IteratorObject<TRow, undefined>
): TRow[] {
  const out: TRow[] = [];
  for (const inc of visibleIncidents(ctx)) {
    for (const row of filter(inc.id)) out.push(row);
  }
  return out;
}

export const chatFeed = spacetimedb.view(
  { name: 'chat_feed', public: true },
  t.array(chatMessages.rowType),
  (ctx) => rowsForIncidents(ctx, (id) => ctx.db.chatMessages.incidentId.filter(id))
);

export const scopeFeed = spacetimedb.view(
  { name: 'scope_feed', public: true },
  t.array(scopeEntries.rowType),
  (ctx) => rowsForIncidents(ctx, (id) => ctx.db.scopeEntries.incidentId.filter(id))
);

export const evidenceFeed = spacetimedb.view(
  { name: 'evidence_feed', public: true },
  t.array(evidence.rowType),
  (ctx) => rowsForIncidents(ctx, (id) => ctx.db.evidence.incidentId.filter(id))
);

export const actionFeed = spacetimedb.view(
  { name: 'action_feed', public: true },
  t.array(actions.rowType),
  (ctx) => rowsForIncidents(ctx, (id) => ctx.db.actions.incidentId.filter(id))
);

export const missionFeed = spacetimedb.view(
  { name: 'mission_feed', public: true },
  t.array(missions.rowType),
  (ctx) => rowsForIncidents(ctx, (id) => ctx.db.missions.incidentId.filter(id))
);

export const approvalFeed = spacetimedb.view(
  { name: 'approval_feed', public: true },
  t.array(approvals.rowType),
  (ctx) => {
    const out = [];
    for (const inc of visibleIncidents(ctx)) {
      for (const a of ctx.db.actions.incidentId.filter(inc.id)) {
        for (const ap of ctx.db.approvals.actionId.filter(a.id)) out.push(ap);
      }
    }
    return out;
  }
);

export const incidentAlertFeed = spacetimedb.view(
  { name: 'incident_alert_feed', public: true },
  t.array(alerts.rowType),
  (ctx) => rowsForIncidents(ctx, (id) => ctx.db.alerts.incidentId.filter(id))
);

export const auditFeed = spacetimedb.view(
  { name: 'audit_feed', public: true },
  t.array(auditEvents.rowType),
  (ctx) => {
    const out = [];
    const isAdmin = principalOf(ctx)?.role === 'admin';
    for (const inc of visibleIncidents(ctx)) {
      for (const e of ctx.db.auditEvents.incidentId.filter(inc.id)) out.push(e);
    }
    if (isAdmin) {
      for (const e of ctx.db.auditEvents.incidentId.filter('')) out.push(e);
    }
    return out;
  }
);

// ---------------------------------------------------------------------------
// Operations feeds — shared lab telemetry visible to human roles only.
// Service principals (device/executor/gateway) get empty sets.
// ---------------------------------------------------------------------------

export const deviceFeed = spacetimedb.view(
  { name: 'device_feed', public: true },
  t.array(devices.rowType),
  (ctx) => (canReadOps(ctx) ? allViaIndex(() => ctx.db.devices.lastSeen.filter(new Range<Timestamp>())) : [])
);

export const zoneFeed = spacetimedb.view(
  { name: 'zone_feed', public: true },
  t.array(zones.rowType),
  (ctx) => (canReadOps(ctx) ? allViaIndex(() => ctx.db.zones.updatedAt.filter(new Range<Timestamp>())) : [])
);

export const assetFeed = spacetimedb.view(
  { name: 'asset_feed', public: true },
  t.array(assets.rowType),
  (ctx) => (canReadOps(ctx) ? allViaIndex(() => ctx.db.assets.updatedAt.filter(new Range<Timestamp>())) : [])
);

export const observationFeed = spacetimedb.view(
  { name: 'observation_feed', public: true },
  t.array(observations.rowType),
  (ctx) =>
    canReadOps(ctx)
      ? allViaIndex(() => ctx.db.observations.receivedAt.filter(new Range<Timestamp>()))
      : []
);

export const opsAlertFeed = spacetimedb.view(
  { name: 'ops_alert_feed', public: true },
  t.array(alerts.rowType),
  (ctx) =>
    canReadOps(ctx)
      ? allViaIndex(() => ctx.db.alerts.createdAt.filter(new Range<Timestamp>()))
      : []
);

export const rfFeed = spacetimedb.view(
  { name: 'rf_feed', public: true },
  t.array(rfFrames.rowType),
  (ctx) => (canReadOps(ctx) ? allViaIndex(() => ctx.db.rfFrames.at.filter(new Range<Timestamp>())) : [])
);

export const healthFeed = spacetimedb.view(
  { name: 'health_feed', public: true },
  t.array(health.rowType),
  (ctx) => (canReadOps(ctx) ? allViaIndex(() => ctx.db.health.lastSeen.filter(new Range<Timestamp>())) : [])
);

// ---------------------------------------------------------------------------
// Service feeds
// ---------------------------------------------------------------------------

// pendingMissions — gateway downlink feed: approved missions awaiting dispatch.
export const pendingMissions = spacetimedb.view(
  { name: 'pending_missions', public: true },
  t.array(missions.rowType),
  (ctx) => {
    if (principalOf(ctx)?.role !== 'gateway') return [];
    return [
      ...ctx.db.missions.state.filter(tagValue<MissionStateValue>('approved')),
    ];
  }
);

// deviceMissions — a device principal sees only its own missions.
export const deviceMissions = spacetimedb.view(
  { name: 'device_missions', public: true },
  t.array(missions.rowType),
  (ctx) => {
    const p = ctx.db.devicePrincipals.identity.find(ctx.sender);
    if (p === null || p.revoked) return [];
    return [...ctx.db.missions.deviceId.filter(p.deviceId)];
  }
);

// executorOutbox — executor service feed: pending + claimed rows it may act on.
export const executorOutbox = spacetimedb.view(
  { name: 'executor_outbox', public: true },
  t.array(outbox.rowType),
  (ctx) => {
    if (principalOf(ctx)?.role !== 'executor') return [];
    return [
      ...ctx.db.outbox.state.filter(tagValue<OutboxStateValue>('pending')),
      ...ctx.db.outbox.state.filter(tagValue<OutboxStateValue>('claimed')),
    ];
  }
);

// pendingApprovals — actions awaiting a commander decision on incidents where
// the caller holds commander-level access.
export const pendingApprovals = spacetimedb.view(
  { name: 'pending_approvals', public: true },
  t.array(actions.rowType),
  (ctx) => {
    const out = [];
    for (const inc of visibleIncidents(ctx)) {
      if (incidentAccessLevel(ctx, inc.id) < accessRank('commander')) continue;
      for (const a of ctx.db.actions.incidentId.filter(inc.id)) {
        if (a.state.tag === 'pending_approval' || a.state.tag === 'proposed') out.push(a);
      }
    }
    return out;
  }
);

// userFeed — admin-only directory of registered principals.
export const userFeed = spacetimedb.view(
  { name: 'user_feed', public: true },
  t.array(usersAndRoles.rowType),
  (ctx) => {
    if (principalOf(ctx)?.role !== 'admin') return [];
    return allViaIndex(() => ctx.db.usersAndRoles.createdAt.filter(new Range<Timestamp>()));
  }
);
