// Canonical telemetry envelope validation (docs/04 "Canonical event payload").
// The MQTT topic supplies the authoritative device_id; a mismatched payload
// field is a forgery attempt and rejected.

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
