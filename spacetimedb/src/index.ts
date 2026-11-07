import { ScheduleAt } from 'spacetimedb';
import spacetimedb from './schema';
import { maintenanceTicks } from './schema';

export { default } from './schema';

// Lifecycle: seed the recurring maintenance tick (every 5s).
export const init = spacetimedb.init((ctx) => {
  ctx.db.maintenanceTicks.insert({
    id: 0n,
    scheduledAt: ScheduleAt.interval(5_000_000n),
  });
});

// Reducers — telemetry ingest & registry
export {
  ingestObservation,
  recordRfFrame,
  upsertHealth,
} from './reducers-ingest';

// Reducers — admin / RBAC / registry
export {
  bootstrapAdmin,
  upsertUserRole,
  revokeUser,
  enrollDevicePrincipal,
  revokeDevicePrincipal,
  upsertDevice,
  upsertZone,
  upsertAsset,
  grantIncidentAccess,
  revokeIncidentAccess,
} from './reducers-admin';

// Reducers — incidents, evidence, scope
export {
  createIncident,
  setIncidentStatus,
  closeIncident,
  attachEvidence,
  updateScope,
} from './reducers-incident';

// Reducers — missions
export {
  assignMission,
  markMissionDispatched,
  recordMissionResult,
  cancelMission,
} from './reducers-mission';

// Reducers — actions, approvals, outbox, verification, maintenance
export {
  proposeAction,
  recordApproval,
  claimOutbox,
  recordExecutorOutcome,
  verifyContainment,
  cancelAction,
  maintenanceTick,
} from './reducers-action';

// Reducers — chat & alerts
export { postChatMessage } from './reducers-chat';
export { raiseAlert, setAlertState } from './reducers-alert';

// Views — role-scoped live projections (the subscription surface for clients)
export * from './views';
