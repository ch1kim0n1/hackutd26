import spacetimedb from './schema';
import type {
  DeviceStatusValue,
  DeviceTypeValue,
  UserRoleValue,
} from './schema';
import {
  audit,
  boundedString,
  grantAccess,
  jsonBounded,
  MAX_PAYLOAD_JSON_BYTES,
  newId,
  requireEnum,
  requireIncidentAccess,
  requireRole,
  tagValue,
} from './lib';
import { SenderError, t } from 'spacetimedb/server';
import { Timestamp } from 'spacetimedb';

const USER_ROLES = [
  'admin',
  'commander',
  'responder',
  'observer',
  'agent',
  'device',
  'executor',
  'gateway',
] as const;
const DEVICE_TYPES = [
  'puck_wifi',
  'puck_contact',
  'puck_ble',
  'rover',
  'kismet',
  'sdr',
  'camera',
  'other',
] as const;
const ACCESS_LEVELS = ['viewer', 'responder', 'commander'] as const;
const SERVICE_ROLES = new Set(['device', 'executor', 'gateway']);

// ---------------------------------------------------------------------------
// User / role management (Winstead R02 — admin only, fully audited)
// ---------------------------------------------------------------------------

// bootstrapAdmin — one-time genesis: the FIRST identity to connect becomes
// admin, but only while the directory is completely empty. After that all
// role changes require an existing admin. Demo/lab bootstrap only.
export const bootstrapAdmin = spacetimedb.reducer(
  { note: t.string() },
  (ctx, args) => {
    if (ctx.db.usersAndRoles.count() !== 0n) {
      throw new SenderError('directory already initialized; admin required');
    }
    const note = boundedString(args.note, 256, 'note');
    ctx.db.usersAndRoles.insert({
      userId: ctx.sender,
      role: tagValue<UserRoleValue>('admin'),
      incidentScope: [],
      revoked: false,
      note: `bootstrap: ${note}`,
      createdAt: ctx.timestamp,
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'user.bootstrap_admin',
      entity: `user:${ctx.sender.toHexString()}`,
      incidentId: '',
      after: { role: 'admin' },
      traceId: newId('tr', ctx),
    });
  }
);

export const upsertUserRole = spacetimedb.reducer(
  {
    userId: t.identity(),
    role: t.string(),
    incidentScope: t.array(t.string()),
    note: t.string(),
  },
  (ctx, args) => {
    requireRole(ctx, 'admin');
    const role = requireEnum(args.role, USER_ROLES, 'role');
    const note = boundedString(args.note, 256, 'note');
    const scope = args.incidentScope.map((s) => boundedString(s, 128, 'incident_scope[]'));
    if (scope.length > 256) throw new SenderError('incident_scope too large');

    const existing = ctx.db.usersAndRoles.userId.find(args.userId);
    const before = existing ?? null;
    const row = {
      userId: args.userId,
      role: tagValue<UserRoleValue>(role),
      incidentScope: scope,
      revoked: false,
      note,
      createdAt: existing?.createdAt ?? ctx.timestamp,
    };
    if (existing === null) ctx.db.usersAndRoles.insert(row);
    else ctx.db.usersAndRoles.userId.update({ ...existing, ...row });

    audit(ctx, {
      actor: ctx.sender,
      operation: existing === null ? 'user.create' : 'user.update_role',
      entity: `user:${args.userId.toHexString()}`,
      incidentId: '',
      before,
      after: row,
      traceId: newId('tr', ctx),
    });
  }
);

export const revokeUser = spacetimedb.reducer(
  { userId: t.identity() },
  (ctx, { userId }) => {
    requireRole(ctx, 'admin');
    if (userId.isEqual(ctx.sender)) {
      throw new SenderError('cannot revoke own admin session');
    }
    const existing = ctx.db.usersAndRoles.userId.find(userId);
    if (existing === null) throw new SenderError('unknown user');
    if (existing.revoked) return; // idempotent
    ctx.db.usersAndRoles.userId.update({ ...existing, revoked: true });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'user.revoke',
      entity: `user:${userId.toHexString()}`,
      incidentId: '',
      before: existing,
      after: { ...existing, revoked: true },
      traceId: newId('tr', ctx),
    });
  }
);

// ---------------------------------------------------------------------------
// Device enrollment — binds a device_id to a SpacetimeDB identity principal.
// ---------------------------------------------------------------------------

export const enrollDevicePrincipal = spacetimedb.reducer(
  { deviceId: t.string(), identity: t.identity() },
  (ctx, args) => {
    requireRole(ctx, 'admin');
    const deviceId = boundedString(args.deviceId, 128, 'device_id');
    if (ctx.db.devices.id.find(deviceId) === null) {
      throw new SenderError(`unknown device: ${deviceId}`);
    }
    const existing = ctx.db.devicePrincipals.deviceId.find(deviceId);
    if (existing !== null) {
      if (existing.identity.isEqual(args.identity) && !existing.revoked) return; // idempotent
      ctx.db.devicePrincipals.deviceId.update({
        ...existing,
        identity: args.identity,
        enrolledBy: ctx.sender,
        enrolledAt: ctx.timestamp,
        revoked: false,
      });
    } else {
      const dup = ctx.db.devicePrincipals.identity.find(args.identity);
      if (dup !== null) throw new SenderError('identity already enrolled for another device');
      ctx.db.devicePrincipals.insert({
        deviceId,
        identity: args.identity,
        enrolledBy: ctx.sender,
        enrolledAt: ctx.timestamp,
        revoked: false,
      });
    }
    audit(ctx, {
      actor: ctx.sender,
      operation: 'device.enroll',
      entity: `device:${deviceId}`,
      incidentId: '',
      after: { deviceId, identity: args.identity.toHexString() },
      traceId: newId('tr', ctx),
    });
  }
);

export const revokeDevicePrincipal = spacetimedb.reducer(
  { deviceId: t.string() },
  (ctx, { deviceId }) => {
    requireRole(ctx, 'admin');
    const existing = ctx.db.devicePrincipals.deviceId.find(deviceId);
    if (existing === null || existing.revoked) return;
    ctx.db.devicePrincipals.deviceId.update({ ...existing, revoked: true });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'device.revoke',
      entity: `device:${deviceId}`,
      incidentId: '',
      before: existing,
      after: { ...existing, revoked: true },
      traceId: newId('tr', ctx),
    });
  }
);

// ---------------------------------------------------------------------------
// Registry: devices, zones, assets (admin-managed lab inventory)
// ---------------------------------------------------------------------------

export const upsertDevice = spacetimedb.reducer(
  {
    id: t.string(),
    type: t.string(),
    zoneId: t.string(),
    firmware: t.string(),
  },
  (ctx, args) => {
    requireRole(ctx, 'admin', 'gateway');
    const id = boundedString(args.id, 128, 'id');
    const type = requireEnum(args.type, DEVICE_TYPES, 'type');
    const zoneId = boundedString(args.zoneId, 128, 'zone_id');
    if (ctx.db.zones.id.find(zoneId) === null) throw new SenderError(`unknown zone: ${zoneId}`);
    const firmware = boundedString(args.firmware, 128, 'firmware');

    const existing = ctx.db.devices.id.find(id);
    const row = {
      id,
      type: tagValue<DeviceTypeValue>(type),
      zoneId,
      status: existing?.status ?? tagValue<DeviceStatusValue>('unknown'),
      lastSeen: existing?.lastSeen ?? new Timestamp(0n),
      lastSeq: existing?.lastSeq ?? 0n,
      firmware,
    };
    if (existing === null) ctx.db.devices.insert(row);
    else ctx.db.devices.id.update(row);
    audit(ctx, {
      actor: ctx.sender,
      operation: existing === null ? 'device.register' : 'device.update',
      entity: `device:${id}`,
      incidentId: '',
      before: existing ?? undefined,
      after: row,
      traceId: newId('tr', ctx),
    });
  }
);

export const upsertZone = spacetimedb.reducer(
  {
    id: t.string(),
    name: t.string(),
    boundsJson: t.string(),
    waypoints: t.array(t.string()),
  },
  (ctx, args) => {
    requireRole(ctx, 'admin');
    const id = boundedString(args.id, 128, 'id');
    const name = boundedString(args.name, 128, 'name');
    const boundsJson = jsonBounded(args.boundsJson, MAX_PAYLOAD_JSON_BYTES, 'bounds_json');
    JSON.parse(boundsJson);
    const waypoints = args.waypoints.map((w) => boundedString(w, 128, 'waypoints[]'));
    if (waypoints.length > 512) throw new SenderError('too many waypoints');

    const existing = ctx.db.zones.id.find(id);
    const row = { id, name, boundsJson, waypoints, updatedAt: ctx.timestamp };
    if (existing === null) ctx.db.zones.insert(row);
    else ctx.db.zones.id.update(row);
  }
);

export const upsertAsset = spacetimedb.reducer(
  {
    id: t.string(),
    zoneId: t.string(),
    type: t.string(),
    owner: t.string(),
    authorizedNetworkIds: t.array(t.string()),
  },
  (ctx, args) => {
    requireRole(ctx, 'admin');
    const id = boundedString(args.id, 128, 'id');
    const zoneId = boundedString(args.zoneId, 128, 'zone_id');
    if (ctx.db.zones.id.find(zoneId) === null) throw new SenderError(`unknown zone: ${zoneId}`);
    const nets = args.authorizedNetworkIds.map((n) =>
      boundedString(n, 128, 'authorized_network_ids[]')
    );
    if (nets.length > 256) throw new SenderError('too many network ids');

    const existing = ctx.db.assets.id.find(id);
    const row = {
      id,
      zoneId,
      type: boundedString(args.type, 64, 'type'),
      owner: boundedString(args.owner, 128, 'owner'),
      authorizedNetworkIds: nets,
      updatedAt: ctx.timestamp,
    };
    if (existing === null) ctx.db.assets.insert(row);
    else ctx.db.assets.id.update(row);
  }
);

// ---------------------------------------------------------------------------
// Incident access grants (scoped RBAC)
// ---------------------------------------------------------------------------

export const grantIncidentAccess = spacetimedb.reducer(
  {
    incidentId: t.string(),
    userId: t.identity(),
    level: t.string(),
  },
  (ctx, args) => {
    const incidentId = boundedString(args.incidentId, 128, 'incident_id');
    const level = requireEnum(args.level, ACCESS_LEVELS, 'level');
    requireIncidentAccess(ctx, incidentId, 'commander');
    const target = ctx.db.usersAndRoles.userId.find(args.userId);
    if (target === null || target.revoked) {
      throw new SenderError('target user is not registered or is revoked');
    }
    if (SERVICE_ROLES.has(target.role.tag)) {
      throw new SenderError('service principals cannot hold incident access');
    }

    const before =
      [...ctx.db.incidentAccess.incidentId.filter(incidentId)].find((g) =>
        g.userId.isEqual(args.userId)
      ) ?? null;
    grantAccess(ctx, incidentId, args.userId, level as 'viewer' | 'responder' | 'commander', ctx.sender);

    audit(ctx, {
      actor: ctx.sender,
      operation: 'incident.grant_access',
      entity: `incident:${incidentId}`,
      incidentId,
      before,
      after: { userId: args.userId.toHexString(), level },
      traceId: newId('tr', ctx),
    });
  }
);

export const revokeIncidentAccess = spacetimedb.reducer(
  { incidentId: t.string(), userId: t.identity() },
  (ctx, args) => {
    const incidentId = boundedString(args.incidentId, 128, 'incident_id');
    requireIncidentAccess(ctx, incidentId, 'commander');
    const incident = ctx.db.incidents.id.find(incidentId);
    if (incident !== null && incident.commanderId.isEqual(args.userId)) {
      throw new SenderError('cannot revoke the incident commander');
    }
    let removed = false;
    for (const g of ctx.db.incidentAccess.incidentId.filter(incidentId)) {
      if (g.userId.isEqual(args.userId)) {
        ctx.db.incidentAccess.id.delete(g.id);
        removed = true;
        break;
      }
    }
    if (removed) {
      audit(ctx, {
        actor: ctx.sender,
        operation: 'incident.revoke_access',
        entity: `incident:${incidentId}`,
        incidentId,
        after: { userId: args.userId.toHexString() },
        traceId: newId('tr', ctx),
      });
    }
  }
);
