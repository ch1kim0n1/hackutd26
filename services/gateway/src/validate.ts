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
]);

export const MAX_PACKET_BYTES = 16 * 1024;
export const MAX_DATA_JSON_BYTES = 8 * 1024;
export const SCHEMA_VERSION = 1;

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
  topicDeviceIdValue: string
): { ok: true; value: NormalizedEnvelope } | { ok: false; reason: string } {
  const strict = validateEnvelope(raw, topicDeviceIdValue);
  if (strict.ok) return { ok: true, value: { ...strict.value, seqAssigned: false } };

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
