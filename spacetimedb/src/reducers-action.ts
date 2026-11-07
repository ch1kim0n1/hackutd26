import spacetimedb from './schema';
import type {
  ActionStateValue,
  ActionTypeValue,
  ApprovalDecisionValue,
  IncidentStatusValue,
  MissionStateValue,
  OutboxStateValue,
} from './schema';
import {
  APPROVAL_DEFAULT_TTL_MICROS,
  APPROVAL_MAX_TTL_MICROS,
  audit,
  boundedString,
  canonicalJson,
  fingerprintOf,
  incidentAccessLevel,
  microsToTimestamp,
  newId,
  nowMicros,
  OUTBOX_CLAIM_TTL_MICROS,
  OUTBOX_MAX_ATTEMPTS,
  postSystemChat,
  requireEnum,
  requireIncidentAccess,
  requireRole,
  tagValue,
  MAX_REASON_CHARS,
  MAX_PAYLOAD_JSON_BYTES,
  jsonBounded,
} from './lib';
import { maintenanceTicks } from './schema';
import { SenderError, t, Range } from 'spacetimedb/server';
import { Timestamp } from 'spacetimedb';

const ACTION_TYPES = [
  'isolate_endpoint',
  'block_ssid',
  'revoke_credential',
  'disable_switch_port',
  'collect_forensics',
  'quarantine_vlan',
] as const;
const APPROVAL_DECISIONS = ['approved', 'rejected'] as const;
const EXECUTOR_OUTCOMES = ['succeeded', 'failed'] as const;

// ---------------------------------------------------------------------------
// proposeAction — responder+ (or agent service) creates a pending action.
// Fingerprint = FNV-1a over canonical {incident,type,target,initiator} gives
// idempotent propose: retries return the existing action instead of duplicating.
// ---------------------------------------------------------------------------
export const proposeAction = spacetimedb.reducer(
  {
    incidentId: t.string(),
    type: t.string(),
    targetId: t.string(),
    reason: t.string(),
  },
  (ctx, args) => {
    const incidentId = boundedString(args.incidentId, 128, 'incident_id');
    const type = requireEnum(args.type, ACTION_TYPES, 'type');
    const targetId = boundedString(args.targetId, 256, 'target_id');
    const reason = boundedString(args.reason, MAX_REASON_CHARS, 'reason');

    const caller = ctx.db.usersAndRoles.userId.find(ctx.sender);
    const isAgent = caller?.role.tag === 'agent';
    if (isAgent) {
      if (ctx.db.incidents.id.find(incidentId) === null) {
        throw new SenderError('unknown incident');
      }
    } else {
      requireIncidentAccess(ctx, incidentId, 'responder');
    }

    const fingerprint = fingerprintOf(
      canonicalJson({ incidentId, type, targetId, initiator: ctx.sender.toHexString() })
    );
    const existing = ctx.db.actions.fingerprint.find(fingerprint);
    if (existing !== null) return; // idempotent propose

    const id = newId('act', ctx);
    const traceId = newId('tr', ctx);
    ctx.db.actions.insert({
      id,
      incidentId,
      type: tagValue<ActionTypeValue>(type),
      targetId,
      initiator: ctx.sender,
      approvalId: undefined,
      fingerprint,
      state: tagValue<ActionStateValue>('pending_approval'),
      reason,
      verificationRef: undefined,
      createdAt: ctx.timestamp,
      updatedAt: ctx.timestamp,
      version: 1n,
      traceId,
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'action.propose',
      entity: `action:${id}`,
      incidentId,
      after: { id, type, targetId, fingerprint },
      traceId,
    });
    postSystemChat(
      ctx,
      incidentId,
      `Action ${id} proposed: ${type} on ${targetId} — awaiting approval`,
      id
    );
  }
);

// ---------------------------------------------------------------------------
// recordApproval — incident commander approves/rejects. Separation of duties:
// approver can never be the proposer.
// ---------------------------------------------------------------------------
export const recordApproval = spacetimedb.reducer(
  {
    actionId: t.string(),
    decision: t.string(),
    expiresAtMicros: t.i64(),
    note: t.string(),
  },
  (ctx, args) => {
    const actionId = boundedString(args.actionId, 128, 'action_id');
    const decision = requireEnum(args.decision, APPROVAL_DECISIONS, 'decision');
    const note = args.note.length > 0 ? boundedString(args.note, MAX_REASON_CHARS, 'note') : '';

    const action = ctx.db.actions.id.find(actionId);
    if (action === null) throw new SenderError('unknown action');
    requireIncidentAccess(ctx, action.incidentId, 'commander');
    if (!['proposed', 'pending_approval'].includes(action.state.tag)) {
      throw new SenderError(`action not awaiting approval (state ${action.state.tag})`);
    }
    if (action.initiator.isEqual(ctx.sender)) {
      throw new SenderError('separation of duties: proposer cannot approve own action');
    }

    const now = nowMicros(ctx);
    const expiresMicros =
      args.expiresAtMicros > 0n ? args.expiresAtMicros : now + APPROVAL_DEFAULT_TTL_MICROS;
    if (expiresMicros <= now) throw new SenderError('approval already expired');
    if (expiresMicros > now + APPROVAL_MAX_TTL_MICROS) {
      throw new SenderError('approval TTL exceeds 60 minutes');
    }

    const approval = ctx.db.approvals.insert({
      id: 0n,
      actorId: ctx.sender,
      actionId,
      decision: tagValue<ApprovalDecisionValue>(decision),
      expiresAt: microsToTimestamp(expiresMicros),
      decidedAt: ctx.timestamp,
      note,
      traceId: newId('tr', ctx),
    });

    const newState = decision === 'approved' ? 'approved' : 'rejected';
    const after = {
      ...action,
      state: tagValue<ActionStateValue>(newState),
      approvalId: approval.id,
      updatedAt: ctx.timestamp,
      version: action.version + 1n,
    };
    ctx.db.actions.id.update(after);
    audit(ctx, {
      actor: ctx.sender,
      operation: decision === 'approved' ? 'action.approve' : 'action.reject',
      entity: `action:${actionId}`,
      incidentId: action.incidentId,
      before: action,
      after,
      detail: { note, expiresAtMicros: expiresMicros.toString() },
      traceId: newId('tr', ctx),
    });
    postSystemChat(
      ctx,
      action.incidentId,
      `Action ${actionId} ${decision === 'approved' ? 'APPROVED' : 'REJECTED'} by commander`,
      actionId
    );
  }
);

// ---------------------------------------------------------------------------
// Outbox — durable queue drained by the executor service via executorOutbox view.
// claimOutbox marks rows claimed; recordExecutorOutcome closes the loop.
// Exactly-once: actionId unique + state machine + claim ownership.
// ---------------------------------------------------------------------------
export const claimOutbox = spacetimedb.reducer(
  { outboxId: t.u64() },
  (ctx, { outboxId }) => {
    requireRole(ctx, 'executor');
    const row = ctx.db.outbox.id.find(outboxId);
    if (row === null) throw new SenderError('unknown outbox row');
    if (row.state.tag !== 'pending') {
      throw new SenderError(`outbox row not claimable (state ${row.state.tag})`);
    }
    const action = ctx.db.actions.id.find(row.actionId);
    if (action !== null && action.state.tag === 'cancelled') {
      ctx.db.outbox.id.update({
        ...row,
        state: tagValue<OutboxStateValue>('dead'),
        resultJson: canonicalJson({ reason: 'action cancelled' }),
      });
      return;
    }
    ctx.db.outbox.id.update({
      ...row,
      state: tagValue<OutboxStateValue>('claimed'),
      attempts: row.attempts + 1,
      claimOwner: ctx.sender.toHexString(),
      claimedAt: ctx.timestamp,
    });
    if (action !== null && action.state.tag === 'enqueued') {
      ctx.db.actions.id.update({
        ...action,
        state: tagValue<ActionStateValue>('executing'),
        updatedAt: ctx.timestamp,
        version: action.version + 1n,
      });
    }
    audit(ctx, {
      actor: ctx.sender,
      operation: 'outbox.claim',
      entity: `outbox:${outboxId}`,
      incidentId: row.incidentId,
      after: { outboxId: outboxId.toString(), claimOwner: ctx.sender.toHexString() },
      traceId: row.traceId,
    });
  }
);

export const recordExecutorOutcome = spacetimedb.reducer(
  {
    outboxId: t.u64(),
    outcome: t.string(),
    verificationRef: t.string(),
    resultJson: t.string(),
  },
  (ctx, args) => {
    requireRole(ctx, 'executor');
    const outcome = requireEnum(args.outcome, EXECUTOR_OUTCOMES, 'outcome');
    const row = ctx.db.outbox.id.find(args.outboxId);
    if (row === null) throw new SenderError('unknown outbox row');
    if (row.state.tag !== 'claimed') {
      throw new SenderError(`outbox row not in claimed state (${row.state.tag})`);
    }
    if (row.claimOwner !== ctx.sender.toHexString()) {
      throw new SenderError('outbox row claimed by a different executor');
    }
    const resultJson =
      args.resultJson.length > 0
        ? jsonBounded(args.resultJson, MAX_PAYLOAD_JSON_BYTES, 'result_json')
        : '';
    if (resultJson.length > 0) JSON.parse(resultJson);
    const verificationRef =
      args.verificationRef.length > 0
        ? boundedString(args.verificationRef, 512, 'verification_ref')
        : '';

    ctx.db.outbox.id.update({
      ...row,
      state: tagValue<OutboxStateValue>(outcome === 'succeeded' ? 'succeeded' : 'failed'),
      resultJson: resultJson.length > 0 ? resultJson : row.resultJson,
    });

    const action = ctx.db.actions.id.find(row.actionId);
    if (action !== null) {
      const actionAfter = {
        ...action,
        state: tagValue<ActionStateValue>(
          outcome === 'succeeded' ? 'succeeded' : 'failed'
        ),
        verificationRef:
          verificationRef.length > 0 ? verificationRef : action.verificationRef,
        updatedAt: ctx.timestamp,
        version: action.version + 1n,
      };
      ctx.db.actions.id.update(actionAfter);
      audit(ctx, {
        actor: ctx.sender,
        operation: outcome === 'succeeded' ? 'action.succeeded' : 'action.failed',
        entity: `action:${action.id}`,
        incidentId: action.incidentId,
        before: action,
        after: actionAfter,
        detail: { verificationRef, resultJson: resultJson.slice(0, 2000) },
        traceId: row.traceId,
      });
      postSystemChat(
        ctx,
        action.incidentId,
        `Action ${action.id} execution ${outcome === 'succeeded' ? 'SUCCEEDED' : 'FAILED'}${verificationRef ? ` — ref: ${verificationRef}` : ''}`,
        action.id
      );
    }
    audit(ctx, {
      actor: ctx.sender,
      operation: 'outbox.outcome',
      entity: `outbox:${args.outboxId}`,
      incidentId: row.incidentId,
      after: { outcome, verificationRef },
      traceId: row.traceId,
    });
  }
);

// verifyContainment — incident commander confirms executor-reported success.
// Only a human commander closes the loop; executor output alone is not proof.
export const verifyContainment = spacetimedb.reducer(
  {
    actionId: t.string(),
    verified: t.bool(),
    note: t.string(),
  },
  (ctx, args) => {
    const actionId = boundedString(args.actionId, 128, 'action_id');
    const action = ctx.db.actions.id.find(actionId);
    if (action === null) throw new SenderError('unknown action');
    requireIncidentAccess(ctx, action.incidentId, 'commander');
    if (action.state.tag !== 'succeeded') {
      throw new SenderError(`action not awaiting verification (state ${action.state.tag})`);
    }
    const note = boundedString(args.note, MAX_REASON_CHARS, 'note');

    const after = {
      ...action,
      state: tagValue<ActionStateValue>(args.verified ? 'verified' : 'failed'),
      updatedAt: ctx.timestamp,
      version: action.version + 1n,
    };
    ctx.db.actions.id.update(after);

    // If the incident was awaiting containment, reflect the verdict.
    const incident = ctx.db.incidents.id.find(action.incidentId);
    if (
      incident !== null &&
      incident.status.tag === 'containment_pending' &&
      args.verified
    ) {
      ctx.db.incidents.id.update({
        ...incident,
        status: tagValue<IncidentStatusValue>('contained'),
        updatedAt: ctx.timestamp,
        version: incident.version + 1n,
      });
    }
    audit(ctx, {
      actor: ctx.sender,
      operation: args.verified ? 'containment.verified' : 'containment.verification_failed',
      entity: `action:${actionId}`,
      incidentId: action.incidentId,
      before: action,
      after,
      detail: { note, verified: args.verified },
      traceId: newId('tr', ctx),
    });
    postSystemChat(
      ctx,
      action.incidentId,
      `Containment ${args.verified ? 'VERIFIED' : 'FAILED VERIFICATION'} for ${actionId}: ${note}`,
      actionId
    );
  }
);

// cancelAction — proposer or incident commander cancels before execution.
export const cancelAction = spacetimedb.reducer(
  { actionId: t.string(), reason: t.string() },
  (ctx, args) => {
    const actionId = boundedString(args.actionId, 128, 'action_id');
    const action = ctx.db.actions.id.find(actionId);
    if (action === null) throw new SenderError('unknown action');
    if (
      !action.initiator.isEqual(ctx.sender) &&
      incidentAccessLevel(ctx, action.incidentId) < 3
    ) {
      throw new SenderError('forbidden: proposer or incident commander required');
    }
    if (
      ['enqueued', 'executing', 'succeeded', 'failed', 'verified', 'cancelled', 'expired'].includes(
        action.state.tag
      )
    ) {
      throw new SenderError(`action not cancellable (state ${action.state.tag})`);
    }
    const reason = boundedString(args.reason, MAX_REASON_CHARS, 'reason');
    const after = {
      ...action,
      state: tagValue<ActionStateValue>('cancelled'),
      updatedAt: ctx.timestamp,
      version: action.version + 1n,
    };
    ctx.db.actions.id.update(after);
    audit(ctx, {
      actor: ctx.sender,
      operation: 'action.cancel',
      entity: `action:${actionId}`,
      incidentId: action.incidentId,
      before: action,
      after,
      detail: { reason },
      traceId: newId('tr', ctx),
    });
  }
);

// ---------------------------------------------------------------------------
// Maintenance tick — scheduled reducer (internal sender, no user authz).
// Expires missions past expiresAt, expires stale approvals, dispatches approved
// actions into the outbox exactly once, requeues stale executor claims, and
// marks exhausted outbox rows dead. Runs every 5s via maintenance_ticks.
// ---------------------------------------------------------------------------
export const maintenanceTick = spacetimedb.reducer(
  { onSchedule: maintenanceTicks },
  { tick: maintenanceTicks.rowType },
  (ctx, { tick }) => {
    void tick;
    const now = nowMicros(ctx);

    // 1) Expire missions past their TTL.
    for (const m of ctx.db.missions.expiresAt.filter(
      new Range<Timestamp>({ tag: 'unbounded' }, { tag: 'included', value: microsToTimestamp(now) })
    )) {
      if (['completed', 'failed', 'expired', 'cancelled'].includes(m.state.tag)) continue;
      ctx.db.missions.id.update({
        ...m,
        state: tagValue<MissionStateValue>('expired'),
        updatedAt: ctx.timestamp,
        version: m.version + 1n,
      });
    }

    // 2) Expire approvals whose TTL lapsed while action still approved.
    for (const a of ctx.db.approvals.expiresAt.filter(
      new Range<Timestamp>({ tag: 'unbounded' }, { tag: 'included', value: microsToTimestamp(now) })
    )) {
      const action = ctx.db.actions.id.find(a.actionId);
      if (action !== null && action.state.tag === 'approved') {
        ctx.db.actions.id.update({
          ...action,
          state: tagValue<ActionStateValue>('expired'),
          updatedAt: ctx.timestamp,
          version: action.version + 1n,
        });
      }
    }

    // 3) Dispatch approved actions into the outbox exactly once (actionId unique).
    for (const action of ctx.db.actions.state.filter(tagValue<ActionStateValue>('approved'))) {
      const approval =
        action.approvalId !== undefined && action.approvalId !== null
          ? ctx.db.approvals.id.find(action.approvalId)
          : null;
      if (approval === null || approval.expiresAt.microsSinceUnixEpoch <= now) continue;
      if (ctx.db.outbox.actionId.find(action.id) !== null) continue; // already enqueued
      ctx.db.outbox.insert({
        id: 0n,
        actionId: action.id,
        incidentId: action.incidentId,
        type: action.type.tag,
        targetId: action.targetId,
        payloadJson: canonicalJson({
          schema_version: 1,
          action_id: action.id,
          incident_id: action.incidentId,
          type: action.type.tag,
          target_id: action.targetId,
          fingerprint: action.fingerprint,
          approval_id: action.approvalId,
        }),
        state: tagValue<OutboxStateValue>('pending'),
        attempts: 0,
        claimOwner: '',
        claimedAt: new Timestamp(0n),
        createdAt: ctx.timestamp,
        resultJson: undefined,
        traceId: action.traceId,
      });
      ctx.db.actions.id.update({
        ...action,
        state: tagValue<ActionStateValue>('enqueued'),
        updatedAt: ctx.timestamp,
        version: action.version + 1n,
      });
      audit(ctx, {
        actor: ctx.sender,
        operation: 'action.enqueued',
        entity: `action:${action.id}`,
        incidentId: action.incidentId,
        after: { outboxActionId: action.id },
        traceId: action.traceId,
      });
    }

    // 4) Requeue stale claims (executor crashed mid-execution).
    const staleBefore = microsToTimestamp(now - OUTBOX_CLAIM_TTL_MICROS);
    for (const row of ctx.db.outbox.claimedAt.filter(
      new Range<Timestamp>({ tag: 'unbounded' }, { tag: 'included', value: staleBefore })
    )) {
      if (row.state.tag !== 'claimed') continue;
      if (row.attempts >= OUTBOX_MAX_ATTEMPTS) {
        ctx.db.outbox.id.update({
          ...row,
          state: tagValue<OutboxStateValue>('dead'),
          resultJson: canonicalJson({ reason: 'claim TTL exceeded max attempts' }),
        });
      } else {
        ctx.db.outbox.id.update({
          ...row,
          state: tagValue<OutboxStateValue>('pending'),
          claimOwner: '',
          claimedAt: new Timestamp(0n),
        });
      }
    }

    // 5) Retry failed outbox rows while attempts remain; dead-letter the rest.
    for (const row of ctx.db.outbox.state.filter(tagValue<OutboxStateValue>('failed'))) {
      if (row.attempts >= OUTBOX_MAX_ATTEMPTS) {
        ctx.db.outbox.id.update({
          ...row,
          state: tagValue<OutboxStateValue>('dead'),
          resultJson: canonicalJson({ reason: 'max attempts exceeded' }),
        });
      } else {
        ctx.db.outbox.id.update({
          ...row,
          state: tagValue<OutboxStateValue>('pending'),
          claimOwner: '',
          claimedAt: new Timestamp(0n),
        });
      }
    }
  }
);


