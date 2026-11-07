import spacetimedb from './schema';
import type { AlertStateValue, SeverityValue } from './schema';
import {
  audit,
  boundedString,
  newId,
  requireEnum,
  requireIncidentAccess,
  requireRole,
  tagValue,
} from './lib';
import { SenderError, t } from 'spacetimedb/server';

const SEVERITIES = ['info', 'low', 'medium', 'high', 'critical'] as const;
const ALERT_STATES = ['open', 'acknowledged', 'resolved', 'suppressed'] as const;

// raiseAlert — manual/agent raise path. The deterministic rules engine
// (issue #18) inserts alerts through the internal helper instead.
export const raiseAlert = spacetimedb.reducer(
  {
    ruleId: t.string(),
    observationIds: t.array(t.u64()),
    severity: t.string(),
    title: t.string(),
  },
  (ctx, args) => {
    requireRole(ctx, 'commander', 'responder', 'agent', 'gateway', 'admin');
    const ruleId = boundedString(args.ruleId, 128, 'rule_id');
    const severity = requireEnum(args.severity, SEVERITIES, 'severity');
    const title = boundedString(args.title, 256, 'title');
    if (args.observationIds.length > 1000) {
      throw new SenderError('too many observation ids');
    }
    for (const id of args.observationIds) {
      if (ctx.db.observations.id.find(id) === null) {
        throw new SenderError(`unknown observation id ${id}`);
      }
    }
    const alert = ctx.db.alerts.insert({
      id: 0n,
      ruleId,
      observationIds: args.observationIds,
      severity: tagValue<SeverityValue>(severity),
      state: tagValue<AlertStateValue>('open'),
      incidentId: '',
      title,
      createdAt: ctx.timestamp,
    });
    audit(ctx, {
      actor: ctx.sender,
      operation: 'alert.raise',
      entity: `alert:${alert.id}`,
      incidentId: '',
      after: { ruleId, severity, title, observationIds: args.observationIds.map(String) },
      traceId: newId('tr', ctx),
    });
  }
);

// setAlertState — acknowledge/resolve/suppress. Incident-linked alerts require
// responder access on that incident; unlinked alerts need responder+ role.
export const setAlertState = spacetimedb.reducer(
  {
    alertId: t.u64(),
    state: t.string(),
    note: t.string(),
  },
  (ctx, args) => {
    const state = requireEnum(args.state, ALERT_STATES, 'state');
    const alert = ctx.db.alerts.id.find(args.alertId);
    if (alert === null) throw new SenderError('unknown alert');
    if (alert.incidentId.length > 0) {
      requireIncidentAccess(ctx, alert.incidentId, 'responder');
    } else {
      requireRole(ctx, 'commander', 'responder', 'admin');
    }
    if (alert.state.tag === state) return; // idempotent
    const before = { ...alert };
    const after = {
      ...alert,
      state: tagValue<AlertStateValue>(state as AlertStateValue['tag']),
      createdAt: alert.createdAt,
    };
    ctx.db.alerts.id.update(after);
    audit(ctx, {
      actor: ctx.sender,
      operation: `alert.${state}`,
      entity: `alert:${args.alertId}`,
      incidentId: alert.incidentId,
      before,
      after,
      detail: { note: args.note.slice(0, 500) },
      traceId: newId('tr', ctx),
    });
  }
);
