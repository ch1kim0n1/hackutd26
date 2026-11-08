import spacetimedb from './schema';
import type { MissionStateValue, MissionTypeValue } from './schema';
import {
  audit,
  boundedString,
  canonicalJson,
  type Ctx,
  microsToTimestamp,
  newId,
  nowMicros,
  postSystemChat,
  requireEnum,
  requireIncidentAccess,
  requireRole,
  tagValue,
  MISSION_MAX_TTL_MICROS,
  MAX_PAYLOAD_JSON_BYTES,
  jsonBounded,
} from './lib';
import { SenderError, t } from 'spacetimedb/server';

const MISSION_TYPES = ['inspect_zone', 'patrol', 'capture_photo', 'return_home', 'hold'] as const;
const DEVICE_STATES = ['accepted', 'navigating', 'completed', 'failed'] as const;

// Mission state machine: approved -> dispatched -> accepted -> navigating ->
// completed|failed ; expired/cancelled are terminal side-exits.
const MISSION_RANK: Record<string, number> = {
  approved: 0,
  dispatched: 1,
  accepted: 2,
  navigating: 3,
  completed: 4,
  failed: 4,
  expired: 4,
  cancelled: 4,
  proposed: -1,
};

function missionCommandJson(
  missionId: string,
  deviceId: string,
  type: string,
  zoneId: string,
  waypoint: string,
  expiresAtMicros: bigint,
  maxSpeedMps: number,
  incidentId: string
): string {
  // Rover mission contract — docs/04. Strict fields, no arbitrary PWM.
  // incident_id is optional passthrough: the mission-shim forwards it into
  // the signed rover mission so inspection evidence/report artifacts carry
  // the originating incident linkage end to end.
  return canonicalJson({
    schema_version: 1,
    command_id: missionId,
    mission_id: missionId,
    device_id: deviceId,
    type,
    zone_id: zoneId,
    waypoint_id: waypoint,
    expires_at: new Date(Number(expiresAtMicros / 1000n)).toISOString(),
    max_speed_mps: maxSpeedMps,
    incident_id: incidentId,
  });
}

// Shared validation for commander-assigned and agent-proposed missions.
function validateMissionTarget(
  ctx: Ctx,
  deviceId: string,
  type: string,
  zoneId: string,
  waypoint: string
): void {
  const device = ctx.db.devices.id.find(deviceId);
  if (device === null) throw new SenderError(`unknown device: ${deviceId}`);
  if (device.type.tag === 'puck_wifi' || device.type.tag === 'puck_contact' || device.type.tag === 'puck_ble') {
    throw new SenderError('puck sensors cannot accept missions');
  }
  const zone = ctx.db.zones.id.find(zoneId);
  if (zone === null) throw new SenderError(`unknown zone: ${zoneId}`);
  if (!zone.waypoints.includes(waypoint)) {
    throw new SenderError(`waypoint ${waypoint} not whitelisted in zone ${zoneId}`);
  }
}

function validateMissionWindow(ctx: Ctx, expiresAtMicros: bigint, maxSpeedMps: number): void {
  const now = nowMicros(ctx);
  if (expiresAtMicros <= now) throw new SenderError('expires_at must be in the future');
  if (expiresAtMicros > now + MISSION_MAX_TTL_MICROS) {
    throw new SenderError('expires_at exceeds 15 minute mission TTL');
  }
  if (!(maxSpeedMps > 0.05 && maxSpeedMps <= 0.5)) {
    throw new SenderError('max_speed_mps must be in (0.05, 0.5]');
  }
}

// assignMission — incident commander assigns a bounded rover/device mission.
// Waypoint must be whitelisted in the target zone; TTL capped at 15 minutes.
export const assignMission = spacetimedb.reducer(
  {
    incidentId: t.string(),
    deviceId: t.string(),
    type: t.string(),
    waypoint: t.string(),
    zoneId: t.string(),
    expiresAtMicros: t.i64(),
    maxSpeedMps: t.f64(),
    traceId: t.string(),
  },
  (ctx, args) => {
    const incidentId = boundedString(args.incidentId, 128, 'incident_id');
    requireIncidentAccess(ctx, incidentId, 'commander');
    if (ctx.db.incidents.id.find(incidentId) === null) throw new SenderError('unknown incident');

    const deviceId = boundedString(args.deviceId, 128, 'device_id');
    const type = requireEnum(args.type, MISSION_TYPES, 'type');
    const zoneId = boundedString(args.zoneId, 128, 'zone_id');
    const waypoint = boundedString(args.waypoint, 128, 'waypoint');
    validateMissionTarget(ctx, deviceId, type, zoneId, waypoint);
    validateMissionWindow(ctx, args.expiresAtMicros, args.maxSpeedMps);
    const traceId = boundedString(args.traceId, 128, 'trace_id');

    const id = newId('mis', ctx);
    const commandJson = missionCommandJson(
      id,
      deviceId,
      type,
      zoneId,
      waypoint,
      args.expiresAtMicros,
      args.maxSpeedMps,
      incidentId
    );
    if (commandJson.length > MAX_PAYLOAD_JSON_BYTES) {
      throw new SenderError('command payload too large');
    }
    jsonBounded(commandJson, MAX_PAYLOAD_JSON_BYTES, 'command_json');

    ctx.db.missions.insert({
      id,
      incidentId,
      deviceId,
      type: tagValue<MissionTypeValue>(type),
      waypoint,
      zoneId,
      state: tagValue<MissionStateValue>('approved'),
      expiresAt: microsToTimestamp(args.expiresAtMicros),
      commandJson,
      resultJson: undefined,
      createdAt: ctx.timestamp,
      updatedAt: ctx.timestamp,
      version: 1n,
      traceId,
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'mission.assign',
      entity: `mission:${id}`,
      incidentId,
      after: { id, deviceId, type, waypoint, zoneId, expiresAtMicros: args.expiresAtMicros.toString() },
      traceId,
    });
    postSystemChat(ctx, incidentId, `Mission ${id} assigned to ${deviceId} (${type} @ ${waypoint})`, id);
  }
);

// proposeMission — investigation agent proposes a bounded mission for
// commander approval (GLUE-03). Same target/window validation as
// assignMission but lands in 'proposed' state: nothing reaches the gateway
// downlink (pendingMissions = 'approved' only) until approveMission.
// Agent identity comes from ctx.sender — never trusted from arguments.
export const proposeMission = spacetimedb.reducer(
  {
    incidentId: t.string(),
    deviceId: t.string(),
    type: t.string(),
    waypoint: t.string(),
    zoneId: t.string(),
    expiresAtMicros: t.i64(),
    maxSpeedMps: t.f64(),
    justification: t.string(),
    traceId: t.string(),
  },
  (ctx, args) => {
    requireRole(ctx, 'agent');
    const incidentId = boundedString(args.incidentId, 128, 'incident_id');
    requireIncidentAccess(ctx, incidentId, 'responder');
    if (ctx.db.incidents.id.find(incidentId) === null) throw new SenderError('unknown incident');

    const deviceId = boundedString(args.deviceId, 128, 'device_id');
    const type = requireEnum(args.type, MISSION_TYPES, 'type');
    const zoneId = boundedString(args.zoneId, 128, 'zone_id');
    const waypoint = boundedString(args.waypoint, 128, 'waypoint');
    validateMissionTarget(ctx, deviceId, type, zoneId, waypoint);
    validateMissionWindow(ctx, args.expiresAtMicros, args.maxSpeedMps);
    const justification = boundedString(args.justification, 2000, 'justification');
    const traceId = boundedString(args.traceId, 128, 'trace_id');

    const id = newId('mis', ctx);
    // Draft command payload stored but unsigned/undispatchable until approval.
    const commandJson = missionCommandJson(
      id, deviceId, type, zoneId, waypoint, args.expiresAtMicros, args.maxSpeedMps,
      incidentId
    );
    if (commandJson.length > MAX_PAYLOAD_JSON_BYTES) {
      throw new SenderError('command payload too large');
    }
    ctx.db.missions.insert({
      id,
      incidentId,
      deviceId,
      type: tagValue<MissionTypeValue>(type),
      waypoint,
      zoneId,
      state: tagValue<MissionStateValue>('proposed'),
      expiresAt: microsToTimestamp(args.expiresAtMicros),
      commandJson,
      resultJson: undefined,
      createdAt: ctx.timestamp,
      updatedAt: ctx.timestamp,
      version: 1n,
      traceId,
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'mission.propose',
      entity: `mission:${id}`,
      incidentId,
      after: { id, deviceId, type, waypoint, zoneId, justification },
      traceId,
    });
    postSystemChat(ctx, incidentId, `Mission ${id} proposed by agent (${type} @ ${waypoint}) — awaiting commander approval`, id);
  }
);

// approveMission — incident commander approves an agent-proposed mission.
// Separation of duties: agents can propose, never approve (requireRole).
export const approveMission = spacetimedb.reducer(
  { missionId: t.string() },
  (ctx, { missionId }) => {
    const mission = ctx.db.missions.id.find(missionId);
    if (mission === null) throw new SenderError('unknown mission');
    requireIncidentAccess(ctx, mission.incidentId, 'commander');
    if (mission.state.tag !== 'proposed') {
      throw new SenderError(`mission not in proposed state (${mission.state.tag})`);
    }
    if (mission.expiresAt.microsSinceUnixEpoch <= nowMicros(ctx)) {
      ctx.db.missions.id.update({
        ...mission,
        state: tagValue<MissionStateValue>('expired'),
        updatedAt: ctx.timestamp,
        version: mission.version + 1n,
      });
      throw new SenderError('mission proposal expired before approval');
    }
    ctx.db.missions.id.update({
      ...mission,
      state: tagValue<MissionStateValue>('approved'),
      updatedAt: ctx.timestamp,
      version: mission.version + 1n,
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'mission.approve',
      entity: `mission:${mission.id}`,
      incidentId: mission.incidentId,
      before: mission,
      after: { state: 'approved' },
      traceId: mission.traceId,
    });
    postSystemChat(ctx, mission.incidentId, `Mission ${mission.id} approved`, mission.id);
  }
);

// markMissionDispatched — gateway service confirms MQTT downlink published.
export const markMissionDispatched = spacetimedb.reducer(
  { missionId: t.string() },
  (ctx, { missionId }) => {
    requireRole(ctx, 'gateway');
    const mission = ctx.db.missions.id.find(missionId);
    if (mission === null) throw new SenderError('unknown mission');
    if (mission.state.tag !== 'approved') {
      throw new SenderError(`mission not dispatchable from state ${mission.state.tag}`);
    }
    if (mission.expiresAt.microsSinceUnixEpoch <= nowMicros(ctx)) {
      ctx.db.missions.id.update({
        ...mission,
        state: tagValue<MissionStateValue>('expired'),
        updatedAt: ctx.timestamp,
        version: mission.version + 1n,
      });
      throw new SenderError('mission expired before dispatch');
    }
    ctx.db.missions.id.update({
      ...mission,
      state: tagValue<MissionStateValue>('dispatched'),
      updatedAt: ctx.timestamp,
      version: mission.version + 1n,
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'mission.dispatched',
      entity: `mission:${missionId}`,
      incidentId: mission.incidentId,
      after: { missionId },
      traceId: mission.traceId,
    });
  }
);

// recordMissionResult — device principal reports its own mission progress.
export const recordMissionResult = spacetimedb.reducer(
  {
    missionId: t.string(),
    state: t.string(),
    resultJson: t.string(),
  },
  (ctx, args) => {
    const principal = ctx.db.devicePrincipals.identity.find(ctx.sender);
    if (principal === null || principal.revoked) {
      throw new SenderError('device principal required');
    }
    const mission = ctx.db.missions.id.find(args.missionId);
    if (mission === null) throw new SenderError('unknown mission');
    if (mission.deviceId !== principal.deviceId) {
      throw new SenderError('mission belongs to a different device');
    }
    const state = requireEnum(args.state, DEVICE_STATES, 'state');
    const from = mission.state.tag;
    const terminal = ['completed', 'failed', 'expired', 'cancelled'].includes(from);
    if (terminal) {
      if (from === state) return; // idempotent terminal replay
      throw new SenderError(`mission already terminal (${from})`);
    }
    const fromRank = MISSION_RANK[from] ?? -1;
    const ok =
      (state === 'accepted' && (from === 'dispatched' || from === 'accepted')) ||
      (state === 'navigating' &&
        (from === 'dispatched' || from === 'accepted' || from === 'navigating')) ||
      ((state === 'completed' || state === 'failed') && fromRank >= MISSION_RANK.dispatched);
    if (!ok) {
      throw new SenderError(`illegal mission transition ${from} -> ${state}`);
    }

    const resultJson =
      args.resultJson.length > 0
        ? jsonBounded(args.resultJson, MAX_PAYLOAD_JSON_BYTES, 'result_json')
        : '';
    if (resultJson.length > 0) JSON.parse(resultJson);

    const after = {
      ...mission,
      state: tagValue<MissionStateValue>(state),
      resultJson: resultJson.length > 0 ? resultJson : mission.resultJson,
      updatedAt: ctx.timestamp,
      version: mission.version + 1n,
    };
    ctx.db.missions.id.update(after);
    audit(ctx, {
      actor: ctx.sender,
      operation: 'mission.result',
      entity: `mission:${mission.id}`,
      incidentId: mission.incidentId,
      before: mission,
      after,
      traceId: mission.traceId,
    });
    if (state === 'completed' || state === 'failed') {
      postSystemChat(
        ctx,
        mission.incidentId,
        `Mission ${mission.id} ${state} (${mission.deviceId})`,
        mission.id
      );
    }
  }
);

// cancelMission — incident commander cancels a non-terminal mission.
export const cancelMission = spacetimedb.reducer(
  { missionId: t.string(), reason: t.string() },
  (ctx, args) => {
    const missionId = boundedString(args.missionId, 128, 'mission_id');
    const mission = ctx.db.missions.id.find(missionId);
    if (mission === null) throw new SenderError('unknown mission');
    requireIncidentAccess(ctx, mission.incidentId, 'commander');
    if (['completed', 'failed', 'expired', 'cancelled'].includes(mission.state.tag)) {
      throw new SenderError(`mission already terminal (${mission.state.tag})`);
    }
    const reason = boundedString(args.reason, 512, 'reason');
    const after = {
      ...mission,
      state: tagValue<MissionStateValue>('cancelled'),
      resultJson: mission.resultJson ?? canonicalJson({ cancel_reason: reason }),
      updatedAt: ctx.timestamp,
      version: mission.version + 1n,
    };
    ctx.db.missions.id.update(after);
    audit(ctx, {
      actor: ctx.sender,
      operation: 'mission.cancel',
      entity: `mission:${missionId}`,
      incidentId: mission.incidentId,
      before: mission,
      after,
      detail: { reason },
      traceId: newId('tr', ctx),
    });
    postSystemChat(ctx, mission.incidentId, `Mission ${missionId} cancelled: ${reason}`, missionId);
  }
);
