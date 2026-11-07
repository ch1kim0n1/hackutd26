import spacetimedb from './schema';
import type { DeviceStatusValue, TrustTierValue } from './schema';
import {
  audit,
  boundedString,
  correlateObservation,
  jsonBounded,
  microsToTimestamp,
  nowMicros,
  OBSERVATION_KINDS,
  OBS_MAX_AGE_MICROS,
  OBS_MAX_FUTURE_SKEW_MICROS,
  MAX_DATA_JSON_BYTES,
  requireEnum,
  requireRole,
  tagValue,
} from './lib';
import { SenderError, t } from 'spacetimedb/server';

const DEVICE_STATUSES = ['online', 'offline', 'degraded', 'fault', 'unknown'] as const;
const TRUST_TIERS = ['device_asserted', 'gateway_validated', 'verified'] as const;
const RF_FRAME_KINDS = ['wifi', 'sdr_fft', 'ble', 'contact', 'other'] as const;

// ingestObservation — the single write path for device telemetry.
// Callers: (a) an enrolled device principal (device_id must match enrollment),
// (b) the collector gateway service (role 'gateway'), which has already
// authenticated the device at the MQTT/transport layer.
// Never trusts caller-supplied principal fields: deviceId is checked against
// the enrolled principal or the gateway role, schema/kind/size/time/seq are
// all validated, and duplicates/replays are dropped before insert.
export const ingestObservation = spacetimedb.reducer(
  {
    eventId: t.string(),
    deviceId: t.string(),
    kind: t.string(),
    seq: t.u64(),
    observedAtMicros: t.i64(),
    zoneId: t.string(),
    dataJson: t.string(),
    trustTier: t.string(),
    traceId: t.string(),
  },
  (ctx, args) => {
    const { eventId, deviceId, kind, seq, observedAtMicros, zoneId, dataJson, trustTier, traceId } = args;

    // --- caller authorization -------------------------------------------
    const devicePrincipal = ctx.db.devicePrincipals.identity.find(ctx.sender);
    let effectiveTrust: TrustTierValue;
    if (devicePrincipal !== null && !devicePrincipal.revoked) {
      if (devicePrincipal.deviceId !== deviceId) {
        throw new SenderError('device principal may only ingest for its own device_id');
      }
      effectiveTrust = tagValue<TrustTierValue>('device_asserted');
    } else {
      requireRole(ctx, 'gateway');
      effectiveTrust = tagValue<TrustTierValue>(
        requireEnum(trustTier, TRUST_TIERS, 'trust_tier')
      );
      if (effectiveTrust.tag === 'verified') {
        throw new SenderError('devices/gateway cannot assert verified trust tier');
      }
    }

    // --- schema / payload validation ------------------------------------
    const eventIdClean = boundedString(eventId, 128, 'event_id');
    const deviceIdClean = boundedString(deviceId, 128, 'device_id');
    const kindClean = boundedString(kind, 64, 'kind');
    if (!OBSERVATION_KINDS.has(kindClean)) {
      throw new SenderError(`unknown observation kind: ${kindClean}`);
    }
    const zoneIdClean = boundedString(zoneId, 128, 'zone_id');
    const dataClean = jsonBounded(dataJson, MAX_DATA_JSON_BYTES, 'data_json');
    try {
      JSON.parse(dataClean);
    } catch {
      throw new SenderError('data_json is not valid JSON');
    }
    const traceClean = boundedString(traceId, 128, 'trace_id');

    const device = ctx.db.devices.id.find(deviceIdClean);
    if (device === null) throw new SenderError(`unknown device: ${deviceIdClean}`);
    if (ctx.db.zones.id.find(zoneIdClean) === null) {
      throw new SenderError(`unknown zone: ${zoneIdClean}`);
    }

    // --- replay / duplicate / freshness ----------------------------------
    const existing = ctx.db.observations.eventId.find(eventIdClean);
    if (existing !== null) {
      if (existing.deviceId !== deviceIdClean) {
        throw new SenderError('event_id already used by a different device');
      }
      return; // exact duplicate: idempotent no-op
    }
    if (seq <= device.lastSeq) {
      throw new SenderError(`stale or replayed seq ${seq} <= lastSeq ${device.lastSeq}`);
    }

    const observedAtMicrosBig = observedAtMicros;
    const observedAt = microsToTimestamp(observedAtMicrosBig);
    const now = nowMicros(ctx);
    if (observedAtMicrosBig > now + OBS_MAX_FUTURE_SKEW_MICROS) {
      throw new SenderError('observed_at is too far in the future');
    }
    if (observedAtMicrosBig < now - OBS_MAX_AGE_MICROS) {
      throw new SenderError('observed_at is older than 24h');
    }

    // --- insert -----------------------------------------------------------
    const obsRow = ctx.db.observations.insert({
      id: 0n,
      eventId: eventIdClean,
      deviceId: deviceIdClean,
      kind: kindClean,
      seq,
      observedAt,
      receivedAt: ctx.timestamp,
      zoneId: zoneIdClean,
      dataJson: dataClean,
      trustTier: effectiveTrust,
      traceId: traceClean,
    });

    // Deterministic correlation (issue #18): alert for matched kinds,
    // incident for incident-tier rules — same transaction, replay-safe.
    correlateObservation(ctx, {
      id: obsRow.id,
      eventId: eventIdClean,
      deviceId: deviceIdClean,
      kind: kindClean,
      observedAt,
      zoneId: zoneIdClean,
      traceId: traceClean,
    });

    ctx.db.devices.id.update({
      ...device,
      status: tagValue<DeviceStatusValue>('online'),
      lastSeen: ctx.timestamp,
      lastSeq: seq,
    });

    audit(ctx, {
      actor: ctx.sender,
      operation: 'ingest.observation',
      entity: `observation:${eventIdClean}`,
      incidentId: '',
      after: {
        eventId: eventIdClean,
        deviceId: deviceIdClean,
        kind: kindClean,
        seq: seq.toString(),
        zoneId: zoneIdClean,
      },
      traceId: traceClean,
    });
  }
);

// recordRfFrame — Kismet/SDR collector metadata pointer (artifact lives outside DB).
export const recordRfFrame = spacetimedb.reducer(
  {
    receiver: t.string(),
    kind: t.string(),
    atMicros: t.i64(),
    artifactRef: t.string(),
    metaJson: t.string(),
  },
  (ctx, args) => {
    requireRole(ctx, 'gateway', 'agent', 'admin');
    const kind = requireEnum(args.kind, RF_FRAME_KINDS, 'kind');
    const meta = jsonBounded(args.metaJson, MAX_DATA_JSON_BYTES, 'meta_json');
    JSON.parse(meta);
    ctx.db.rfFrames.insert({
      id: 0n,
      receiver: boundedString(args.receiver, 128, 'receiver'),
      kind,
      at: microsToTimestamp(args.atMicros),
      artifactRef: boundedString(args.artifactRef, 512, 'artifact_ref'),
      metaJson: meta,
    });
  }
);

// upsertHealth — component heartbeat from any service principal.
export const upsertHealth = spacetimedb.reducer(
  {
    component: t.string(),
    status: t.string(),
    detail: t.string(),
  },
  (ctx, args) => {
    requireRole(ctx, 'gateway', 'executor', 'agent', 'admin', 'commander');
    const status = requireEnum(args.status, DEVICE_STATUSES, 'status');
    const component = boundedString(args.component, 128, 'component');
    const detail = args.detail.length > 512 ? args.detail.slice(0, 512) : args.detail;
    const existing = ctx.db.health.component.find(component);
    const row = {
      component,
      status: tagValue<DeviceStatusValue>(status),
      detail,
      lastSeen: ctx.timestamp,
    };
    if (existing === null) ctx.db.health.insert(row);
    else ctx.db.health.component.update({ ...existing, ...row });
  }
);
