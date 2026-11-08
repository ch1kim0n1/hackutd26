// Module commandJson -> signed rover mission contract.
//
// The module emits docs/04 commandJson:
//   {schema_version, command_id, mission_id, device_id, type, zone_id,
//    waypoint_id, expires_at, max_speed_mps}
// The rover (robotics/rover) requires its own contract: per-type fields,
// device-matched type names, and an HMAC-SHA256 `signature` over the
// canonical JSON (sorted keys, compact separators, signature excluded).
//
// Canonicalization MUST be byte-identical to rover_mission/auth.py:
// json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True).
// We therefore reject non-ASCII strings — JS JSON.stringify and Python
// json.dumps diverge there, which would break signature verification.

import { createHmac } from 'node:crypto';
import type { DeviceShimConfig } from './config.js';

const MODULE_TO_ROVER_TYPE: Record<string, string> = {
  inspect_zone: 'inspect_zone',
  patrol: 'patrol_route',
  capture_photo: 'capture_photo',
  return_home: 'return_home',
  hold: 'stop',
};

const DEFAULT_CAMERA_ID = 'cam-mast';

export type TransformResult =
  | { ok: true; mission: Record<string, unknown> }
  | { ok: false; reason: string };

/** Deterministic canonical JSON — must match Python's
 *  json.dumps(sort_keys=True, separators=(",", ":")) for ASCII input. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(',')}]`;
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return `{${keys
    .map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`)
    .join(',')}}`;
}

function isAscii(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    if (s.charCodeAt(i) > 0x7f) return false;
  }
  return true;
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null;
}

export function signMission(mission: Record<string, unknown>, secret: string): string {
  // Matches rover_mission/auth.py: signature field excluded from payload.
  const { signature: _sig, ...unsigned } = mission;
  return createHmac('sha256', secret).update(canonicalJson(unsigned)).digest('hex');
}

/** Transform + sign one commandJson payload for `deviceId`.
 *  Returns the complete rover mission dict incl. `signature`. */
export function transformCommand(
  raw: unknown,
  deviceId: string,
  cfg: DeviceShimConfig,
  secret: string
): TransformResult {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ok: false, reason: 'payload is not an object' };
  }
  const cmd = raw as Record<string, unknown>;
  if (cmd.schema_version !== 1) return { ok: false, reason: 'bad_schema_version' };
  const missionId = str(cmd.mission_id);
  const commandId = str(cmd.command_id);
  const cmdDevice = str(cmd.device_id);
  const moduleType = str(cmd.type);
  const expiresAt = str(cmd.expires_at);
  if (!missionId || !commandId || !moduleType || !expiresAt) {
    return { ok: false, reason: 'missing mission_id/command_id/type/expires_at' };
  }
  if (cmdDevice !== deviceId) {
    return { ok: false, reason: 'device_id does not match command topic' };
  }
  if (Number.isNaN(Date.parse(expiresAt))) {
    return { ok: false, reason: 'expires_at is not a valid timestamp' };
  }
  const roverType = MODULE_TO_ROVER_TYPE[moduleType];
  if (!roverType) return { ok: false, reason: `unmapped mission type ${moduleType}` };

  const mission: Record<string, unknown> = {
    schema_version: 1,
    command_id: commandId,
    mission_id: missionId,
    device_id: deviceId,
    type: roverType,
    expires_at: expiresAt,
  };
  const speed = cmd.max_speed_mps;
  if (typeof speed === 'number' && Number.isFinite(speed) && speed > 0) {
    mission.max_speed_mps = speed;
  }

  const zoneId = str(cmd.zone_id);
  const waypointId = str(cmd.waypoint_id);

  switch (roverType) {
    case 'inspect_zone': {
      if (!zoneId || !waypointId) {
        return { ok: false, reason: 'inspect_zone needs zone_id+waypoint_id' };
      }
      mission.zone_id = zoneId;
      mission.waypoint_id = waypointId;
      break;
    }
    case 'patrol_route': {
      const routeId = waypointId
        ? (cfg.routes?.[waypointId] ?? cfg.routes?.['*'])
        : cfg.routes?.['*'];
      if (!routeId) {
        return { ok: false, reason: `no route mapping for waypoint ${waypointId ?? ''}` };
      }
      mission.route_id = routeId;
      break;
    }
    case 'capture_photo': {
      mission.camera_id = cfg.camera_id ?? DEFAULT_CAMERA_ID;
      break;
    }
    case 'return_home':
    case 'stop':
      break;
    default:
      return { ok: false, reason: `internal: unmapped rover type ${roverType}` };
  }

  // Optional incident linkage — the module commandJson does not emit it
  // today, but when a producer includes it the rover propagates it into
  // inspection/evidence artifacts unchanged (still HMAC-covered).
  const incidentId = str(cmd.incident_id);
  if (incidentId) mission.incident_id = incidentId;

  // ASCII guard — keeps canonical bytes identical to Python's
  // ensure_ascii=True output so the rover's HMAC verifies.
  for (const v of Object.values(mission)) {
    if (typeof v === 'string' && !isAscii(v)) {
      return { ok: false, reason: 'non-ascii field would break signature' };
    }
  }

  mission.signature = signMission(mission, secret);
  return { ok: true, mission };
}
