// Shared rover mission/telemetry/evidence contract — sentinel.rover.* v1.
//
// Issue #115 / docs/14. TypeScript port of rover_mission/common.py: the
// versioned schema plus mapping tables between the SpacetimeDB module
// commandJson, the signed rover mission, autonomy directives and telemetry/
// evidence records. transform.ts remains the production signing path; this
// module adds the common-schema surface and the device-local
// wireless_rescan leg the module cannot express.

import { signMission, transformCommand, type TransformResult } from './transform.js';
import type { DeviceShimConfig } from './config.js';

export const SCHEMA_VERSION = 1;
export const CONTRACT_MISSION = 'sentinel.rover.mission';
export const CONTRACT_TELEMETRY = 'sentinel.rover.telemetry';
export const CONTRACT_EVIDENCE = 'sentinel.rover.evidence';
export const CONTRACT_DIRECTIVE = 'sentinel.rover.autonomy_directive';

export const PROVENANCE_VALUES = ['DEMO', 'REPLAY', 'LIVE'] as const;
export type Provenance = (typeof PROVENANCE_VALUES)[number];

export const COMMON_MISSION_TYPES = [
  'inspect_zone', 'patrol', 'capture_photo', 'return_home', 'hold',
  'wireless_rescan',
] as const;
export const MODULE_MISSION_TYPES = [
  'inspect_zone', 'patrol', 'capture_photo', 'return_home', 'hold',
] as const;
export const ROVER_MISSION_TYPES = [
  'inspect_zone', 'patrol_route', 'capture_photo',
  'wireless_rescan', 'return_home', 'stop',
] as const;
export type CommonMissionType = (typeof COMMON_MISSION_TYPES)[number];

const TYPE_TO_ROVER: Record<CommonMissionType, string> = {
  inspect_zone: 'inspect_zone',
  patrol: 'patrol_route',
  capture_photo: 'capture_photo',
  return_home: 'return_home',
  hold: 'stop',
  wireless_rescan: 'wireless_rescan',
};
const TYPE_FROM_ROVER: Record<string, CommonMissionType> = Object.fromEntries(
  Object.entries(TYPE_TO_ROVER).map(([k, v]) => [v, k as CommonMissionType])
);

const MISSION_REQUIRED_FIELDS: Record<CommonMissionType, string[]> = {
  inspect_zone: ['zone_id', 'waypoint_id'],
  patrol: [],
  capture_photo: [],
  return_home: [],
  hold: [],
  wireless_rescan: ['zone_id'],
};
const MISSION_ANY_OF_FIELDS: Partial<Record<CommonMissionType, string[][]>> = {
  patrol: [['waypoint_id', 'route_id']],
};
const MODULE_REQUIRED_FIELDS: Record<string, string[]> = {
  inspect_zone: ['zone_id', 'waypoint_id'],
  patrol: ['zone_id', 'waypoint_id'],
  capture_photo: ['zone_id', 'waypoint_id'],
  return_home: ['zone_id', 'waypoint_id'],
  hold: ['zone_id', 'waypoint_id'],
};
const MODULE_SPEED_MIN = 0.05;
const MODULE_SPEED_MAX = 0.5;

export const COMMON_STATES = [
  'proposed', 'approved', 'dispatched', 'queued',
  'accepted', 'navigating', 'scanning',
  'completed', 'failed', 'aborted', 'timed_out',
  'expired', 'cancelled',
] as const;
export type CommonState = (typeof COMMON_STATES)[number];

// Only these states may be device-reported to the module
// (DEVICE_STATES in reducers-mission.ts / MISSION_STATUS_DEVICE_STATES in
// lib.ts). aborted/timed_out project to 'failed' with the native outcome
// preserved in the reason prefix — see docs/14 §4.
export const STATE_TO_MODULE_DEVICE: Record<string, string | null> = {
  accepted: 'accepted',
  navigating: 'navigating',
  scanning: 'navigating',
  completed: 'completed',
  failed: 'failed',
  aborted: 'failed',
  timed_out: 'failed',
  queued: null,
  proposed: null,
  approved: null,
  dispatched: null,
  expired: null,
  cancelled: null,
};

export const POSE_UNITS = ['mm', 'm'] as const;
export const ROVER_POSE_UNIT = 'mm';
export const ROVER_POSE_FRAME = 'surveyed_floorplan';
export const AUTONOMY_POSE_UNIT = 'm';
export const AUTONOMY_POSE_FRAME = 'autonomy_map';

export interface CommonPose {
  x: number;
  y: number;
  heading_rad: number;
  unit: 'mm' | 'm';
  frame: string;
  confidence?: number;
  source?: string;
}

export interface CommonMission {
  contract: typeof CONTRACT_MISSION;
  schema_version: number;
  mission_id: string;
  command_id: string;
  device_id: string;
  type: CommonMissionType;
  zone_id?: string;
  waypoint_id?: string;
  route_id?: string;
  camera_id?: string;
  expires_at: string;
  max_speed_mps?: number;
  issued_at?: string;
}

export interface CommonTelemetry {
  contract: typeof CONTRACT_TELEMETRY;
  schema_version: number;
  event: string;
  device_id: string;
  mission_id?: string;
  command_id?: string;
  type?: CommonMissionType;
  state?: CommonState;
  zone_id?: string;
  waypoint_id?: string;
  pose?: CommonPose;
  reason?: string;
  observed_at: string;
  provenance: Provenance;
  data?: Record<string, unknown>;
}

export interface CommonEvidence {
  contract: typeof CONTRACT_EVIDENCE;
  schema_version: number;
  artifact_id: string;
  mission_id: string;
  device_id: string;
  zone_id: string;
  waypoint_id?: string;
  command_id?: string;
  camera_id?: string;
  observed_at: string;
  received_at?: string;
  storage_ref: string;
  sha256: string;
  bytes: number;
  pose?: CommonPose;
  synthetic: boolean;
  provenance: Provenance;
  width?: number;
  height?: number;
  format?: string;
}

function isStr(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0;
}
function isAscii(s: string): boolean {
  for (let i = 0; i < s.length; i++) if (s.charCodeAt(i) > 0x7f) return false;
  return true;
}
function checkAsciiStrings(m: Record<string, unknown>): string | null {
  for (const [k, v] of Object.entries(m)) {
    if (typeof v === 'string' && !isAscii(v)) return `non-ascii field ${k}`;
  }
  return null;
}
function parseIso(s: string): number {
  return Date.parse(s);
}
function validPose(p: unknown): p is CommonPose {
  if (p === null || typeof p !== 'object') return false;
  const o = p as Record<string, unknown>;
  return (
    typeof o.x === 'number' && typeof o.y === 'number' &&
    typeof o.heading_rad === 'number' &&
    (o.unit === 'mm' || o.unit === 'm') && isStr(o.frame)
  );
}

export function poseFromRover(pose: Record<string, unknown>): CommonPose {
  const out: CommonPose = {
    x: pose.x_mm as number,
    y: pose.y_mm as number,
    heading_rad: pose.heading_rad as number,
    unit: ROVER_POSE_UNIT,
    frame: ROVER_POSE_FRAME,
  };
  if (pose.confidence !== undefined && pose.confidence !== null) {
    out.confidence = pose.confidence as number;
  }
  if (pose.source) out.source = pose.source as string;
  return out;
}

export function poseFromAutonomy(
  pose: readonly number[],
  source = 'odometry+scan_match'
): CommonPose {
  return {
    x: pose[0], y: pose[1], heading_rad: pose[2],
    unit: AUTONOMY_POSE_UNIT, frame: AUTONOMY_POSE_FRAME, source,
  };
}

// ---------------------------------------------------------------------------
// Validators — same (ok, reason) contract as rover_mission.common.
// ---------------------------------------------------------------------------

export function validateCommonMission(m: unknown): [boolean, string] {
  if (m === null || typeof m !== 'object' || Array.isArray(m)) {
    return [false, 'not an object'];
  }
  const o = m as Record<string, unknown>;
  if (o.contract !== CONTRACT_MISSION) return [false, 'bad_contract'];
  if (o.schema_version !== SCHEMA_VERSION) return [false, 'bad_schema_version'];
  for (const f of ['mission_id', 'command_id', 'device_id', 'type']) {
    if (!isStr(o[f])) return [false, `missing_${f}`];
  }
  const bad = checkAsciiStrings(o);
  if (bad) return [false, bad];
  const mtype = o.type as CommonMissionType;
  if (!COMMON_MISSION_TYPES.includes(mtype)) return [false, 'unknown_type'];
  for (const f of MISSION_REQUIRED_FIELDS[mtype]) {
    if (!isStr(o[f])) return [false, `missing_${f}`];
  }
  for (const group of MISSION_ANY_OF_FIELDS[mtype] ?? []) {
    if (!group.some((f) => isStr(o[f]))) {
      return [false, `missing_${group.join('|')}`];
    }
  }
  const speed = o.max_speed_mps;
  if (
    speed !== undefined && speed !== null &&
    (typeof speed !== 'number' || !Number.isFinite(speed) || speed <= 0)
  ) {
    return [false, 'bad_max_speed_mps'];
  }
  if (!isStr(o.expires_at)) return [false, 'missing_expires_at'];
  if (Number.isNaN(parseIso(o.expires_at))) return [false, 'bad_expires_at'];
  return [true, ''];
}

export function validateCommonTelemetry(t: unknown): [boolean, string] {
  if (t === null || typeof t !== 'object' || Array.isArray(t)) {
    return [false, 'not an object'];
  }
  const o = t as Record<string, unknown>;
  if (o.contract !== CONTRACT_TELEMETRY) return [false, 'bad_contract'];
  if (o.schema_version !== SCHEMA_VERSION) return [false, 'bad_schema_version'];
  if (!isStr(o.event) || !isStr(o.device_id)) {
    return [false, 'missing_event_or_device'];
  }
  if (!PROVENANCE_VALUES.includes(o.provenance as Provenance)) {
    return [false, 'bad_provenance'];
  }
  if (!isStr(o.observed_at)) return [false, 'missing_observed_at'];
  if (Number.isNaN(parseIso(o.observed_at))) return [false, 'bad_observed_at'];
  for (const f of ['mission_id', 'command_id', 'zone_id', 'waypoint_id']) {
    if (o[f] !== undefined && o[f] !== null && !isStr(o[f])) {
      return [false, `bad_${f}`];
    }
  }
  if (o.type !== undefined && o.type !== null &&
      !COMMON_MISSION_TYPES.includes(o.type as CommonMissionType)) {
    return [false, 'unknown_type'];
  }
  if (o.state !== undefined && o.state !== null &&
      !COMMON_STATES.includes(o.state as CommonState)) {
    return [false, 'unknown_state'];
  }
  if (o.pose !== undefined && o.pose !== null && !validPose(o.pose)) {
    return [false, 'bad_pose'];
  }
  if (o.data !== undefined && o.data !== null &&
      (typeof o.data !== 'object' || Array.isArray(o.data))) {
    return [false, 'bad_data'];
  }
  return [true, ''];
}

export function validateCommonEvidence(e: unknown): [boolean, string] {
  if (e === null || typeof e !== 'object' || Array.isArray(e)) {
    return [false, 'not an object'];
  }
  const o = e as Record<string, unknown>;
  if (o.contract !== CONTRACT_EVIDENCE) return [false, 'bad_contract'];
  if (o.schema_version !== SCHEMA_VERSION) return [false, 'bad_schema_version'];
  for (const f of ['artifact_id', 'mission_id', 'device_id', 'zone_id',
                   'observed_at', 'storage_ref']) {
    if (!isStr(o[f])) return [false, `missing_${f}`];
  }
  const sha = o.sha256;
  if (typeof sha !== 'string' || sha.length !== 64 ||
      !/^[0-9a-f]{64}$/.test(sha)) {
    return [false, 'bad_sha256'];
  }
  if (typeof o.bytes !== 'number' || !Number.isInteger(o.bytes) || o.bytes < 0) {
    return [false, 'bad_bytes'];
  }
  if (!PROVENANCE_VALUES.includes(o.provenance as Provenance)) {
    return [false, 'bad_provenance'];
  }
  if (typeof o.synthetic !== 'boolean') return [false, 'missing_synthetic'];
  for (const f of ['command_id', 'waypoint_id', 'camera_id']) {
    if (o[f] !== undefined && o[f] !== null && !isStr(o[f])) {
      return [false, `bad_${f}`];
    }
  }
  if (o.pose !== undefined && o.pose !== null && !validPose(o.pose)) {
    return [false, 'bad_pose'];
  }
  if (Number.isNaN(parseIso(o.observed_at as string))) {
    return [false, 'bad_observed_at'];
  }
  return [true, ''];
}

// ---------------------------------------------------------------------------
// Mission mappers
// ---------------------------------------------------------------------------

const OPTIONAL_MISSION_FIELDS = [
  'zone_id', 'waypoint_id', 'route_id', 'camera_id',
  'expires_at', 'max_speed_mps', 'issued_at',
] as const;

function commonMissionFrom(m: Record<string, unknown>, mtype: CommonMissionType): CommonMission {
  const out: Record<string, unknown> = {
    contract: CONTRACT_MISSION,
    schema_version: SCHEMA_VERSION,
    mission_id: m.mission_id,
    command_id: m.command_id ?? m.mission_id,
    device_id: m.device_id,
    type: mtype,
  };
  for (const f of OPTIONAL_MISSION_FIELDS) {
    if (m[f] !== undefined && m[f] !== null) out[f] = m[f];
  }
  return out as unknown as CommonMission;
}

/** SpacetimeDB commandJson -> common mission. null if not module-shaped. */
export function commandToCommon(cmd: unknown): CommonMission | null {
  if (cmd === null || typeof cmd !== 'object' || Array.isArray(cmd)) return null;
  const o = cmd as Record<string, unknown>;
  if (o.schema_version !== SCHEMA_VERSION) return null;
  const mtype = o.type as CommonMissionType;
  if (!MODULE_MISSION_TYPES.includes(mtype as never)) return null;
  if (!isStr(o.mission_id) || !isStr(o.device_id)) return null;
  const common = commonMissionFrom(o, mtype);
  const [ok] = validateCommonMission(common);
  return ok ? common : null;
}

/** Common mission -> SpacetimeDB commandJson (module boundary rules). */
export function commonToCommand(common: unknown): Record<string, unknown> | null {
  const [ok] = validateCommonMission(common);
  if (!ok) return null;
  const c = common as CommonMission;
  if (!MODULE_MISSION_TYPES.includes(c.type as never)) return null;
  for (const f of MODULE_REQUIRED_FIELDS[c.type] ?? []) {
    if (!isStr((c as unknown as Record<string, unknown>)[f])) return null;
  }
  const speed = c.max_speed_mps;
  if (typeof speed !== 'number' || !Number.isFinite(speed) ||
      !(speed > MODULE_SPEED_MIN && speed <= MODULE_SPEED_MAX)) {
    return null;
  }
  return {
    schema_version: SCHEMA_VERSION,
    command_id: c.command_id,
    mission_id: c.mission_id,
    device_id: c.device_id,
    type: c.type,
    zone_id: c.zone_id,
    waypoint_id: c.waypoint_id,
    expires_at: c.expires_at,
    max_speed_mps: c.max_speed_mps,
  };
}

/** Rover mission dict (signed or unsigned) -> common mission. */
export function roverToCommon(mission: unknown): CommonMission | null {
  if (mission === null || typeof mission !== 'object' || Array.isArray(mission)) {
    return null;
  }
  const o = mission as Record<string, unknown>;
  const rtype = o.type as string;
  const mtype = TYPE_FROM_ROVER[rtype];
  if (!mtype) return null;
  if (!isStr(o.mission_id) || !isStr(o.device_id)) return null;
  const common = commonMissionFrom(o, mtype);
  const [ok] = validateCommonMission(common);
  return ok ? common : null;
}

const ROVER_EVENT_ENVELOPE = new Set([
  'event', 'schema_version', 'device_id', 'mission_id', 'command_id',
  'type', 'state', 'zone_id', 'waypoint_id', 'pose_confidence', 'reason',
  'observed_at', 'pose',
]);

/** rover_mission _emit payload -> common telemetry. */
export function roverEventToCommon(
  event: unknown,
  provenance: Provenance = 'DEMO'
): CommonTelemetry | null {
  if (event === null || typeof event !== 'object' || Array.isArray(event)) {
    return null;
  }
  const o = event as Record<string, unknown>;
  if (o.schema_version !== SCHEMA_VERSION) return null;
  if (!isStr(o.event) || !isStr(o.device_id)) return null;
  const out: Record<string, unknown> = {
    contract: CONTRACT_TELEMETRY,
    schema_version: SCHEMA_VERSION,
    event: o.event,
    device_id: o.device_id,
    observed_at: o.observed_at ?? '',
    provenance,
  };
  for (const f of ['mission_id', 'command_id', 'zone_id', 'waypoint_id', 'reason']) {
    if (o[f]) out[f] = o[f];
  }
  const rtype = o.type as string;
  if (rtype && TYPE_FROM_ROVER[rtype]) out.type = TYPE_FROM_ROVER[rtype];
  if (typeof o.state === 'string' &&
      (COMMON_STATES as readonly string[]).includes(o.state)) {
    out.state = o.state;
  }
  if (o.pose !== null && typeof o.pose === 'object' && !Array.isArray(o.pose)) {
    out.pose = poseFromRover(o.pose as Record<string, unknown>);
  }
  const extras: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(o)) {
    if (!ROVER_EVENT_ENVELOPE.has(k)) extras[k] = v;
  }
  if (Object.keys(extras).length > 0) out.data = extras;
  const [ok] = validateCommonTelemetry(out);
  return ok ? (out as unknown as CommonTelemetry) : null;
}

/** autonomy {pose:[x,y,th], mode} report -> common telemetry. */
export function autonomyReportToCommon(
  report: unknown,
  deviceId: string,
  provenance: Provenance = 'DEMO',
  observedAt?: string
): CommonTelemetry | null {
  if (report === null || typeof report !== 'object' || Array.isArray(report)) {
    return null;
  }
  const o = report as Record<string, unknown>;
  const pose = o.pose;
  if (!Array.isArray(pose) || pose.length < 3) return null;
  const out: Record<string, unknown> = {
    contract: CONTRACT_TELEMETRY,
    schema_version: SCHEMA_VERSION,
    event: 'pose_report',
    device_id: deviceId,
    pose: poseFromAutonomy(pose as number[]),
    provenance,
    observed_at: observedAt ?? new Date().toISOString(),
  };
  if (o.mode) out.data = { mode: o.mode };
  const [ok] = validateCommonTelemetry(out);
  return ok ? (out as unknown as CommonTelemetry) : null;
}

/** Common evidence (rover sidecar/EvidenceRef shape) -> validated common. */
export function evidenceToCommon(
  evidence: unknown,
  opts: { device_id?: string; provenance?: Provenance; mission_id?: string } = {}
): CommonEvidence | null {
  if (evidence === null || typeof evidence !== 'object' || Array.isArray(evidence)) {
    return null;
  }
  const o = evidence as Record<string, unknown>;
  if (!isStr(o.artifact_id) || !isStr(o.sha256)) return null;
  const synthetic = Boolean(o.synthetic);
  const out: Record<string, unknown> = {
    contract: CONTRACT_EVIDENCE,
    schema_version: SCHEMA_VERSION,
    artifact_id: o.artifact_id,
    mission_id: opts.mission_id ?? o.mission_id ?? '',
    device_id: opts.device_id ?? o.device_id ?? '',
    zone_id: o.zone_id ?? '',
    observed_at: o.observed_at ?? '',
    storage_ref: o.storage_ref ?? o.path ?? '',
    sha256: o.sha256,
    bytes: o.bytes ?? 0,
    synthetic,
    provenance: opts.provenance ?? (synthetic ? 'DEMO' : 'LIVE'),
  };
  for (const f of ['command_id', 'waypoint_id', 'camera_id', 'received_at',
                   'width', 'height', 'format']) {
    if (o[f] !== undefined && o[f] !== null) out[f] = o[f];
  }
  if (o.pose !== null && typeof o.pose === 'object' && !Array.isArray(o.pose)) {
    out.pose = poseFromRover(o.pose as Record<string, unknown>);
  }
  const [ok] = validateCommonEvidence(out);
  return ok ? (out as unknown as CommonEvidence) : null;
}

/** Common evidence -> SpacetimeDB evidence row shape (schema.ts). */
export function commonToModuleEvidenceRow(
  common: unknown,
  ctx: { incident_id: string; trust_tier: string; trace_id: string }
): Record<string, unknown> | null {
  const [ok] = validateCommonEvidence(common);
  if (!ok) return null;
  const c = common as CommonEvidence;
  const source = c.camera_id ?? 'rover-camera';
  return {
    incidentId: ctx.incident_id,
    source: `rover/${c.device_id}/${source}`,
    observedAt: c.observed_at,
    storageRef: c.storage_ref,
    sha256: c.sha256,
    trustTier: ctx.trust_tier,
    traceId: ctx.trace_id,
  };
}

/** Common state -> module device-reportable {state, reason} or null. */
export function moduleReportFields(
  state: string,
  reason = ''
): { state: string; reason: string } | null {
  const mapped = STATE_TO_MODULE_DEVICE[state];
  if (mapped === undefined || mapped === null) return null;
  return { state: mapped, reason: reason ? `${state}:${reason}` : state };
}

// ---------------------------------------------------------------------------
// Common -> signed rover mission (mission-shim translation point).
// Module-dispatchable types reuse transform.ts verbatim; wireless_rescan is
// the device-local leg the module cannot express (docs/14 §5).
// ---------------------------------------------------------------------------

function isAsciiRecord(m: Record<string, unknown>): boolean {
  return Object.values(m).every(
    (v) => typeof v !== 'string' || isAscii(v)
  );
}

function directRoverBuild(
  c: CommonMission,
  deviceId: string,
  secret: string,
  fields: Record<string, unknown>
): TransformResult {
  const mission: Record<string, unknown> = {
    schema_version: SCHEMA_VERSION,
    command_id: c.command_id,
    mission_id: c.mission_id,
    device_id: deviceId,
    expires_at: c.expires_at,
    ...fields,
  };
  if (c.max_speed_mps !== undefined) mission.max_speed_mps = c.max_speed_mps;
  if (!isAsciiRecord(mission)) {
    return { ok: false, reason: 'non-ascii field would break signature' };
  }
  mission.signature = signMission(mission, secret);
  return { ok: true, mission };
}

export function commonToRoverMission(
  common: unknown,
  deviceId: string,
  cfg: DeviceShimConfig,
  secret: string
): TransformResult {
  const [ok] = validateCommonMission(common);
  if (!ok) return { ok: false, reason: 'invalid common mission' };
  const c = common as CommonMission;
  if (c.device_id !== deviceId) {
    return { ok: false, reason: 'device_id does not match shim device' };
  }

  // Explicit route_id wins over cfg resolution — preserves rover-native
  // patrol missions that never carried a module waypoint selector.
  if (c.type === 'patrol' && isStr(c.route_id)) {
    return directRoverBuild(c, deviceId, secret, {
      type: 'patrol_route', route_id: c.route_id,
    });
  }
  if (c.type === 'wireless_rescan') {
    // device-local leg: same envelope + signature rules as transform.ts,
    // minus the module leg (no module type exists for it — docs/14 §5).
    const fields: Record<string, unknown> = { type: 'wireless_rescan' };
    if (c.zone_id) fields.zone_id = c.zone_id;
    if (c.waypoint_id) fields.waypoint_id = c.waypoint_id;
    return directRoverBuild(c, deviceId, secret, fields);
  }

  const cmd = commonToCommand(c);
  if (cmd === null) {
    return { ok: false, reason: 'not module-dispatchable' };
  }
  return transformCommand(cmd, deviceId, cfg, secret);
}
