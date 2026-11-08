// Canonical telemetry envelope validation (docs/04 "Canonical event payload").
// The MQTT topic supplies the authoritative device_id; a mismatched payload
// field is a forgery attempt and rejected.

// Keep in sync with spacetimedb/src/lib.ts OBSERVATION_KINDS.
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
  // Data-center node telemetry (apps/datacenter; docs/13 section 5).
  'service_inventory',
  'network_flow',
  'resource_metric',
  'config_drift',
]);

export const MAX_PACKET_BYTES = 16 * 1024;
export const MAX_DATA_JSON_BYTES = 8 * 1024;
export const SCHEMA_VERSION = 1;

import { createHmac, timingSafeEqual } from 'node:crypto';

// ---------------------------------------------------------------------------
// Device payload signatures (sensors/pucks Observation.canonical()):
// HMAC-SHA256 over the 8 envelope fields as sorted-keys compact JSON —
// byte-identical to python json.dumps(sort_keys=True, separators=(",", ":"),
// ensure_ascii=True) for ASCII input. Non-ASCII strings diverge between the
// two serializers, so any non-ASCII string in the signed body fails verify
// rather than guessing.
// ---------------------------------------------------------------------------

const SIGNED_FIELDS = [
  'schema_version',
  'event_id',
  'device_id',
  'seq',
  'observed_at',
  'kind',
  'zone_id',
  'data',
] as const;

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const obj = value as Record<string, unknown>;
  return `{${Object.keys(obj)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`)
    .join(',')}}`;
}

function isAsciiDeep(v: unknown): boolean {
  if (typeof v === 'string') {
    for (let i = 0; i < v.length; i++) if (v.charCodeAt(i) > 0x7f) return false;
    return true;
  }
  if (Array.isArray(v)) return v.every(isAsciiDeep);
  if (v !== null && typeof v === 'object') {
    const o = v as Record<string, unknown>;
    return Object.keys(o).every((k) => {
      for (let i = 0; i < k.length; i++) if (k.charCodeAt(i) > 0x7f) return false;
      return isAsciiDeep(o[k]);
    });
  }
  return true;
}

/** Verify a canonical-envelope `signature` against the device HMAC secret. */
export function verifyDeviceSignature(p: Record<string, unknown>, secret: string): boolean {
  const sig = typeof p.signature === 'string' ? p.signature : '';
  if (!/^[0-9a-f]{64}$/.test(sig)) return false;
  const body: Record<string, unknown> = {};
  for (const f of SIGNED_FIELDS) body[f] = p[f];
  if (!isAsciiDeep(body)) return false;
  const expected = createHmac('sha256', secret).update(canonicalJson(body)).digest('hex');
  return timingSafeEqual(Buffer.from(sig), Buffer.from(expected));
}

export interface TelemetryEnvelope {
  schemaVersion: number;
  eventId: string;
  deviceId: string;
  seq: bigint;
  observedAtMicros: bigint;
  kind: string;
  zoneId: string;
  dataJson: string;
  traceId: string;
}

export type ValidationResult =
  | { ok: true; value: TelemetryEnvelope }
  | { ok: false; reason: string };

const MAX_STR = 128;

function bounded(s: unknown, field: string): string | null {
  if (typeof s !== 'string') return null;
  const t = s.trim();
  if (t.length === 0 || t.length > MAX_STR) return null;
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f-\u009f]/.test(t)) return null;
  return t;
}

/** deviceId comes from the MQTT topic, never from the payload. */
export function topicDeviceId(topic: string, prefix: string): string | null {
  const parts = topic.split('/');
  // <prefix>/<device_id>/telemetry  (prefix may itself contain '/'))
  const prefixParts = prefix.split('/').length;
  if (parts.length !== prefixParts + 2) return null;
  if (parts.slice(0, prefixParts).join('/') !== prefix) return null;
  if (parts[prefixParts + 1] !== 'telemetry') return null;
  const id = bounded(parts[prefixParts], 'device_id');
  return id;
}

export function validateEnvelope(
  raw: Buffer | string,
  topicDeviceIdValue: string
): ValidationResult {
  const text = typeof raw === 'string' ? raw : raw.toString('utf8');
  if (Buffer.byteLength(text, 'utf8') > MAX_PACKET_BYTES) {
    return { ok: false, reason: 'packet exceeds 16KiB' };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, reason: 'payload is not valid JSON' };
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, reason: 'payload is not an object' };
  }
  const p = parsed as Record<string, unknown>;

  if (p.schema_version !== SCHEMA_VERSION) {
    return { ok: false, reason: `unsupported schema_version ${String(p.schema_version)}` };
  }
  const eventId = bounded(p.event_id, 'event_id');
  const deviceId = bounded(p.device_id, 'device_id');
  const kind = bounded(p.kind, 'kind');
  const zoneId = bounded(p.zone_id, 'zone_id');
  const traceId = bounded(p.trace_id ?? '', 'trace_id') ?? '';
  if (!eventId || !deviceId || !kind || !zoneId) {
    return { ok: false, reason: 'missing or invalid required string field' };
  }
  if (deviceId !== topicDeviceIdValue) {
    return { ok: false, reason: 'device_id does not match telemetry topic' };
  }
  if (!OBSERVATION_KINDS.has(kind)) {
    return { ok: false, reason: `unknown observation kind: ${kind}` };
  }
  if (typeof p.seq !== 'number' || !Number.isInteger(p.seq) || p.seq < 0 || p.seq > Number.MAX_SAFE_INTEGER) {
    return { ok: false, reason: 'seq must be a non-negative safe integer' };
  }
  if (typeof p.observed_at !== 'string') {
    return { ok: false, reason: 'observed_at must be an ISO-8601 string' };
  }
  const observedMs = Date.parse(p.observed_at);
  if (Number.isNaN(observedMs)) {
    return { ok: false, reason: 'observed_at is not a valid timestamp' };
  }
  if (p.data === undefined || p.data === null || typeof p.data !== 'object' || Array.isArray(p.data)) {
    return { ok: false, reason: 'data must be a JSON object' };
  }
  const dataJson = JSON.stringify(p.data);
  if (Buffer.byteLength(dataJson, 'utf8') > MAX_DATA_JSON_BYTES) {
    return { ok: false, reason: 'data exceeds 8KiB' };
  }

  return {
    ok: true,
    value: {
      schemaVersion: SCHEMA_VERSION,
      eventId,
      deviceId,
      seq: BigInt(p.seq),
      observedAtMicros: BigInt(observedMs) * 1000n,
      kind,
      zoneId,
      dataJson,
      traceId,
    },
  };
}

// ---------------------------------------------------------------------------
// Rover mission-runtime telemetry (robotics/rover) -> canonical envelope.
// The rover emits state-transition events {event, mission_id, command_id,
// state, zone_id, pose, ...} without event_id/seq/kind. The gateway assigns
// a per-device monotonic seq (persisted) and synthesizes event_id from the
// mission transition identity so SpacetimeDB replay/dedupe still applies.
// ---------------------------------------------------------------------------

export interface NormalizedEnvelope extends Omit<TelemetryEnvelope, 'seq'> {
  /** 0n => gateway must assign next per-device seq. */
  seq: bigint;
  seqAssigned: boolean;
}

export function normalizeTelemetry(
  raw: Buffer | string,
  topicDeviceIdValue: string,
  hmacKeys: Record<string, string> = {}
): { ok: true; value: NormalizedEnvelope } | { ok: false; reason: string } {
  const strict = validateEnvelope(raw, topicDeviceIdValue);
  if (strict.ok) {
    // Devices with a provisioned HMAC key MUST present a valid signature
    // (payload integrity from firmware to gateway — broker ACLs only
    // authenticate the channel, not the bytes).
    const secret = hmacKeys[topicDeviceIdValue];
    if (secret) {
      let parsed: Record<string, unknown> | null = null;
      try {
        parsed = JSON.parse(typeof raw === 'string' ? raw : raw.toString('utf8')) as Record<string, unknown>;
      } catch {
        return { ok: false, reason: 'signature check failed: unparseable body' };
      }
      if (!verifyDeviceSignature(parsed, secret)) {
        return { ok: false, reason: 'device signature invalid or missing' };
      }
    }
    return { ok: true, value: { ...strict.value, seqAssigned: false } };
  }

  // The legacy rover fallback is unsigned. A keyed device must never reach
  // it by submitting a malformed canonical envelope or a rover-shaped body.
  if (hmacKeys[topicDeviceIdValue]) {
    return { ok: false, reason: 'keyed device requires a signed canonical envelope' };
  }

  const text = typeof raw === 'string' ? raw : raw.toString('utf8');
  if (Buffer.byteLength(text, 'utf8') > MAX_PACKET_BYTES) {
    return { ok: false, reason: 'packet exceeds 16KiB' };
  }
  let p: Record<string, unknown>;
  try {
    p = JSON.parse(text) as Record<string, unknown>;
  } catch {
    return { ok: false, reason: strict.reason };
  }
  if (p === null || typeof p !== 'object' || Array.isArray(p)) {
    return { ok: false, reason: strict.reason };
  }

  // Rover shape: schema_version + mission_id + state + event.
  const isRover =
    p.schema_version === SCHEMA_VERSION &&
    typeof p.mission_id === 'string' &&
    typeof p.state === 'string' &&
    typeof p.event === 'string';
  if (!isRover) return { ok: false, reason: strict.reason };

  const missionId = bounded(p.mission_id, 'mission_id');
  const commandId = bounded(p.command_id ?? '', 'command_id') ?? '';
  const event = bounded(p.event, 'event');
  const zoneId = bounded(p.zone_id ?? '', 'zone_id');
  const observedAt = bounded(p.observed_at ?? '', 'observed_at');
  if (!missionId || !event || !zoneId || !observedAt) {
    return { ok: false, reason: 'rover event missing mission_id/event/zone_id/observed_at' };
  }
  const observedMs = Date.parse(observedAt);
  if (Number.isNaN(observedMs)) {
    return { ok: false, reason: 'rover observed_at invalid' };
  }
  const payloadDevice = bounded(p.device_id ?? '', 'device_id');
  if (payloadDevice !== null && payloadDevice !== topicDeviceIdValue) {
    return { ok: false, reason: 'device_id does not match telemetry topic' };
  }

  // data carries the rover-specific fields; strip envelope-level keys.
  const { schema_version, event: _e, mission_id, command_id, device_id, state, zone_id, observed_at, ...rest } = p;
  void schema_version; void _e; void mission_id; void command_id; void device_id;
  void state; void zone_id; void observed_at;
  const data = {
    mission_id: missionId,
    command_id: commandId,
    state: p.state,
    type: p.type,
    reason: p.reason,
    pose_confidence: p.pose_confidence,
    pose: p.pose,
    ...rest,
  };
  const dataJson = JSON.stringify(data);
  if (Buffer.byteLength(dataJson, 'utf8') > MAX_DATA_JSON_BYTES) {
    return { ok: false, reason: 'data exceeds 8KiB' };
  }

  const eventId = `${topicDeviceIdValue}:${missionId}:${commandId || 'na'}:${event}:${observedMs}`
    .slice(0, MAX_STR);
  return {
    ok: true,
    value: {
      schemaVersion: SCHEMA_VERSION,
      eventId,
      deviceId: topicDeviceIdValue,
      seq: 0n,
      observedAtMicros: BigInt(observedMs) * 1000n,
      kind: 'mission_status',
      zoneId,
      dataJson,
      traceId: bounded(p.trace_id ?? '', 'trace_id') ?? `rover:${missionId}`,
      seqAssigned: true,
    },
  };
}
