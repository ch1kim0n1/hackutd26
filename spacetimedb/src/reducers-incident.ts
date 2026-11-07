import spacetimedb from './schema';
import type {
  ConfidenceValue,
  ImpactDimensionValue,
  ImpactStatusValue,
  IncidentStatusValue,
  SeverityValue,
  TrustTierValue,
} from './schema';
import {
  audit,
  boundedString,
  INCIDENT_TRANSITIONS,
  insertIncident,
  MAX_DESCRIPTION_CHARS,
  MAX_REASON_CHARS,
  microsToTimestamp,
  newId,
  nowMicros,
  requireEnum,
  requireIncidentAccess,
  requireRole,
  tagValue,
  type Ctx,
} from './lib';
import { SenderError, t } from 'spacetimedb/server';

const SEVERITIES = ['info', 'low', 'medium', 'high', 'critical'] as const;
const CONFIDENCES = ['unknown', 'suspected', 'confirmed'] as const;
const INCIDENT_STATUSES = [
  'new',
  'triage',
  'investigating',
  'containment_pending',
  'contained',
  'recovery',
  'resolved',
  'closed',
  'dismissed',
] as const;
const TRUST_TIERS = ['device_asserted', 'gateway_validated', 'verified'] as const;
const DIMS = ['confidentiality', 'integrity', 'availability'] as const;
const IMPACT_STATUSES = [
  'unknown',
  'suspected_exposed',
  'confirmed_exposed',
  'exfiltrated',
  'encrypted_locked',
  'corrupted',
  'unavailable',
  'contained',
  'restored',
  'unaffected',
] as const;
const SHA256_RE = /^[0-9a-f]{64}$/;

// createIncident — Commander/Responder/Admin. Sets caller as incident commander.
export const createIncident = spacetimedb.reducer(
  {
    title: t.string(),
    description: t.string(),
    severity: t.string(),
    confidence: t.string(),
    traceId: t.string(),
  },
  (ctx, args) => {
    requireRole(ctx, 'commander', 'responder', 'admin');
    const severity = requireEnum(args.severity, SEVERITIES, 'severity');
    const confidence = requireEnum(args.confidence, CONFIDENCES, 'confidence');
    const traceId = boundedString(args.traceId, 128, 'trace_id');
    insertIncident(ctx, {
      title: args.title,
      description: args.description,
      severity: severity as SeverityValue['tag'],
      confidence: confidence as ConfidenceValue['tag'],
      status: 'new',
      commanderId: ctx.sender,
      traceId,
    });
  }
);

function transitionIncident(
  ctx: Ctx,
  args: {
    incidentId: string;
    status: string;
    expectedVersion: bigint;
    note: string;
    operation: string;
  }
): void {
  const incidentId = boundedString(args.incidentId, 128, 'incident_id');
  const status = requireEnum(args.status, INCIDENT_STATUSES, 'status');
  requireIncidentAccess(ctx, incidentId, 'commander');
  const incident = ctx.db.incidents.id.find(incidentId);
  if (incident === null) throw new SenderError('unknown incident');
  if (incident.version !== args.expectedVersion) {
    throw new SenderError(
      `version conflict: expected ${args.expectedVersion}, current ${incident.version}`
    );
  }
  const from = incident.status.tag;
  if (!INCIDENT_TRANSITIONS[from].includes(status)) {
    throw new SenderError(`illegal incident transition ${from} -> ${status}`);
  }
  const note = boundedString(args.note, MAX_REASON_CHARS, 'note');
  const after = {
    ...incident,
    status: tagValue<IncidentStatusValue>(status as IncidentStatusValue['tag']),
    updatedAt: ctx.timestamp,
    version: incident.version + 1n,
  };
  ctx.db.incidents.id.update(after);
  audit(ctx, {
    actor: ctx.sender,
    operation: args.operation,
    entity: `incident:${incidentId}`,
    incidentId,
    before: incident,
    after,
    detail: { note, from, to: status },
    traceId: newId('tr', ctx),
  });
}

// setIncidentStatus — commander-level access + optimistic version check.
export const setIncidentStatus = spacetimedb.reducer(
  {
    incidentId: t.string(),
    status: t.string(),
    expectedVersion: t.u64(),
    note: t.string(),
  },
  (ctx, args) => {
    transitionIncident(ctx, { ...args, operation: 'incident.set_status' });
  }
);

export const closeIncident = spacetimedb.reducer(
  {
    incidentId: t.string(),
    status: t.string(),
    expectedVersion: t.u64(),
    note: t.string(),
  },
  (ctx, args) => {
    const status = requireEnum(args.status, ['resolved', 'closed', 'dismissed'], 'status');
    transitionIncident(ctx, { ...args, status, operation: 'incident.close' });
  }
);

// attachEvidence — responder+ on the incident. Binary stays in object store;
// only ref + sha256 + provenance land in SpacetimeDB (ADR-008).
export const attachEvidence = spacetimedb.reducer(
  {
    incidentId: t.string(),
    source: t.string(),
    observedAtMicros: t.i64(),
    storageRef: t.string(),
    sha256: t.string(),
    trustTier: t.string(),
    traceId: t.string(),
  },
  (ctx, args) => {
    const incidentId = boundedString(args.incidentId, 128, 'incident_id');
    requireIncidentAccess(ctx, incidentId, 'responder');
    if (ctx.db.incidents.id.find(incidentId) === null) throw new SenderError('unknown incident');
    const trustTier = requireEnum(args.trustTier, TRUST_TIERS, 'trust_tier');
    const sha = args.sha256.trim().toLowerCase();
    if (!SHA256_RE.test(sha)) throw new SenderError('sha256 must be 64 lowercase hex chars');
    const storageRef = boundedString(args.storageRef, 512, 'storage_ref');
    const source = boundedString(args.source, 128, 'source');
    const traceId = boundedString(args.traceId, 128, 'trace_id');

    const observedAt = microsToTimestamp(args.observedAtMicros);
    const now = nowMicros(ctx);
    if (args.observedAtMicros > now + 5n * 60n * 1_000_000n) {
      throw new SenderError('observed_at is too far in the future');
    }

    ctx.db.evidence.insert({
      id: 0n,
      incidentId,
      source,
      observedAt,
      storageRef,
      sha256: sha,
      trustTier: tagValue<TrustTierValue>(trustTier),
      traceId,
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'incident.attach_evidence',
      entity: `incident:${incidentId}`,
      incidentId,
      after: { storageRef, sha256: sha, source, trustTier },
      traceId,
    });
  }
);

// updateScope — responder+; upsert keyed by (incident, asset, dataset_category)
// with optimistic versioning and full before/after snapshots in audit detail.
export const updateScope = spacetimedb.reducer(
  {
    incidentId: t.string(),
    assetId: t.string(),
    datasetCategory: t.string(),
    impactDimensions: t.array(t.string()),
    impactStatuses: t.array(t.string()),
    estimatedRecords: t.u64(),
    evidenceRefs: t.array(t.string()),
    note: t.string(),
    expectedVersion: t.u64(),
  },
  (ctx, args) => {
    const incidentId = boundedString(args.incidentId, 128, 'incident_id');
    requireIncidentAccess(ctx, incidentId, 'responder');
    if (ctx.db.incidents.id.find(incidentId) === null) throw new SenderError('unknown incident');
    const assetId = boundedString(args.assetId, 128, 'asset_id');
    const datasetCategory = boundedString(args.datasetCategory, 128, 'dataset_category');
    const note = boundedString(args.note, MAX_REASON_CHARS, 'note');

    const dims = [
      ...new Set(
        args.impactDimensions.map((d) =>
          requireEnum(d, DIMS, 'impact_dimensions[]') as ImpactDimensionValue['tag']
        )
      ),
    ];
    const stats = [
      ...new Set(
        args.impactStatuses.map((s) =>
          requireEnum(s, IMPACT_STATUSES, 'impact_statuses[]') as ImpactStatusValue['tag']
        )
      ),
    ];
    if (dims.length === 0 || stats.length === 0) {
      throw new SenderError('impact_dimensions and impact_statuses must be non-empty');
    }
    const evidenceRefs = args.evidenceRefs.map((r) => boundedString(r, 256, 'evidence_refs[]'));
    if (evidenceRefs.length > 64) throw new SenderError('too many evidence refs');

    const existing =
      [...ctx.db.scopeEntries.incidentId.filter(incidentId)].find(
        (row) => row.assetId === assetId && row.datasetCategory === datasetCategory
      ) ?? null;

    const dimValues = dims.map((d) => tagValue<ImpactDimensionValue>(d));
    const statValues = stats.map((s) => tagValue<ImpactStatusValue>(s));

    if (existing === null) {
      if (args.expectedVersion !== 0n) {
        throw new SenderError('expectedVersion must be 0 when creating a scope entry');
      }
      ctx.db.scopeEntries.insert({
        id: 0n,
        incidentId,
        assetId,
        datasetCategory,
        impactDimensions: dimValues,
        impactStatuses: statValues,
        estimatedRecords: args.estimatedRecords,
        evidenceRefs,
        reviewer: ctx.sender,
        note,
        updatedAt: ctx.timestamp,
        version: 1n,
      });
      audit(ctx, {
        actor: ctx.sender,
        operation: 'scope.create',
        entity: `scope:${incidentId}:${assetId}:${datasetCategory}`,
        incidentId,
        after: {
          assetId,
          datasetCategory,
          dims,
          stats,
          estimatedRecords: args.estimatedRecords.toString(),
        },
        traceId: newId('tr', ctx),
      });
      return;
    }

    if (existing.version !== args.expectedVersion) {
      throw new SenderError(
        `version conflict: expected ${args.expectedVersion}, current ${existing.version}`
      );
    }
    const before = { ...existing };
    const after = {
      ...existing,
      impactDimensions: dimValues,
      impactStatuses: statValues,
      estimatedRecords: args.estimatedRecords,
      evidenceRefs,
      reviewer: ctx.sender,
      note,
      updatedAt: ctx.timestamp,
      version: existing.version + 1n,
    };
    ctx.db.scopeEntries.id.update(after);
    audit(ctx, {
      actor: ctx.sender,
      operation: 'scope.update',
      entity: `scope:${incidentId}:${assetId}:${datasetCategory}`,
      incidentId,
      before,
      after,
      detail: { note },
      traceId: newId('tr', ctx),
    });
  }
);
