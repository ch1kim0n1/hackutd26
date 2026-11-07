import { schema, table, t, type Infer } from 'spacetimedb/server';

// ---------------------------------------------------------------------------
// Shared enum types (SATS sum types). Names are unique across the typespace.
// ---------------------------------------------------------------------------

export const DeviceType = t.enum('DeviceType', [
  'puck_wifi',
  'puck_contact',
  'puck_ble',
  'rover',
  'kismet',
  'sdr',
  'camera',
  'other',
]);

export const DeviceStatus = t.enum('DeviceStatus', [
  'online',
  'offline',
  'degraded',
  'fault',
  'unknown',
]);

export const TrustTier = t.enum('TrustTier', [
  'device_asserted',
  'gateway_validated',
  'verified',
]);

export const Severity = t.enum('Severity', [
  'info',
  'low',
  'medium',
  'high',
  'critical',
]);

export const AlertState = t.enum('AlertState', [
  'open',
  'acknowledged',
  'resolved',
  'suppressed',
]);

export const IncidentStatus = t.enum('IncidentStatus', [
  'new',
  'triage',
  'investigating',
  'containment_pending',
  'contained',
  'recovery',
  'resolved',
  'closed',
  'dismissed',
]);

export const Confidence = t.enum('Confidence', [
  'unknown',
  'suspected',
  'confirmed',
]);

export const IncidentAccessLevel = t.enum('IncidentAccessLevel', [
  'viewer',
  'responder',
  'commander',
]);

export const UserRole = t.enum('UserRole', [
  'admin',
  'commander',
  'responder',
  'observer',
  'agent',
  'device',
  'executor',
  'gateway',
]);

export const MissionType = t.enum('MissionType', [
  'inspect_zone',
  'patrol',
  'capture_photo',
  'return_home',
  'hold',
]);

export const MissionState = t.enum('MissionState', [
  'proposed',
  'approved',
  'dispatched',
  'accepted',
  'navigating',
  'completed',
  'failed',
  'expired',
  'cancelled',
]);

export const ImpactDimension = t.enum('ImpactDimension', [
  'confidentiality',
  'integrity',
  'availability',
]);

export const ImpactStatus = t.enum('ImpactStatus', [
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
]);

export const ActionType = t.enum('ActionType', [
  'isolate_endpoint',
  'block_ssid',
  'revoke_credential',
  'disable_switch_port',
  'collect_forensics',
  'quarantine_vlan',
]);

export const ActionState = t.enum('ActionState', [
  'proposed',
  'pending_approval',
  'approved',
  'rejected',
  'enqueued',
  'executing',
  'succeeded',
  'failed',
  'verified',
  'expired',
  'cancelled',
]);

export const ApprovalDecision = t.enum('ApprovalDecision', [
  'approved',
  'rejected',
]);

export const OutboxState = t.enum('OutboxState', [
  'pending',
  'claimed',
  'succeeded',
  'failed',
  'dead',
]);

export const ChatKind = t.enum('ChatKind', ['user', 'system']);

export type DeviceTypeValue = Infer<typeof DeviceType>;
export type DeviceStatusValue = Infer<typeof DeviceStatus>;
export type TrustTierValue = Infer<typeof TrustTier>;
export type SeverityValue = Infer<typeof Severity>;
export type AlertStateValue = Infer<typeof AlertState>;
export type IncidentStatusValue = Infer<typeof IncidentStatus>;
export type ConfidenceValue = Infer<typeof Confidence>;
export type IncidentAccessLevelValue = Infer<typeof IncidentAccessLevel>;
export type UserRoleValue = Infer<typeof UserRole>;
export type MissionTypeValue = Infer<typeof MissionType>;
export type MissionStateValue = Infer<typeof MissionState>;
export type ImpactDimensionValue = Infer<typeof ImpactDimension>;
export type ImpactStatusValue = Infer<typeof ImpactStatus>;
export type ActionTypeValue = Infer<typeof ActionType>;
export type ActionStateValue = Infer<typeof ActionState>;
export type ApprovalDecisionValue = Infer<typeof ApprovalDecision>;
export type OutboxStateValue = Infer<typeof OutboxState>;
export type ChatKindValue = Infer<typeof ChatKind>;

// Row builders reused as reducer-argument / view-return types.
export const ImpactDimensionList = t.array(ImpactDimension);
export const ImpactStatusList = t.array(ImpactStatus);
export const U64List = t.array(t.u64());
export const StringList = t.array(t.string());

// ---------------------------------------------------------------------------
// Tables — all private. Clients read through the role-scoped views in views.ts.
// ---------------------------------------------------------------------------

const devices = table(
  { name: 'devices', public: false },
  {
    id: t.string().primaryKey(),
    type: DeviceType,
    zoneId: t.string().index('btree'),
    status: DeviceStatus,
    lastSeen: t.timestamp().index('btree'),
    lastSeq: t.u64(),
    firmware: t.string(),
  }
);

const zones = table(
  { name: 'zones', public: false },
  {
    id: t.string().primaryKey(),
    name: t.string(),
    boundsJson: t.string(),
    waypoints: StringList,
    updatedAt: t.timestamp().index('btree'),
  }
);

const assets = table(
  { name: 'assets', public: false },
  {
    id: t.string().primaryKey(),
    zoneId: t.string().index('btree'),
    type: t.string(),
    owner: t.string(),
    authorizedNetworkIds: StringList,
    updatedAt: t.timestamp().index('btree'),
  }
);

const devicePrincipals = table(
  { name: 'device_principals', public: false },
  {
    deviceId: t.string().primaryKey(),
    identity: t.identity().unique(),
    enrolledBy: t.identity(),
    enrolledAt: t.timestamp(),
    revoked: t.bool(),
  }
);

const observations = table(
  { name: 'observations', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    eventId: t.string().unique(),
    deviceId: t.string().index('btree'),
    kind: t.string().index('btree'),
    seq: t.u64(),
    observedAt: t.timestamp().index('btree'),
    receivedAt: t.timestamp().index('btree'),
    zoneId: t.string().index('btree'),
    dataJson: t.string(),
    trustTier: TrustTier,
    traceId: t.string(),
  }
);

const alerts = table(
  { name: 'alerts', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    ruleId: t.string().index('btree'),
    observationIds: U64List,
    severity: Severity,
    state: AlertState,
    incidentId: t.string().index('btree'),
    title: t.string(),
    createdAt: t.timestamp().index('btree'),
  }
);

const incidents = table(
  { name: 'incidents', public: false },
  {
    id: t.string().primaryKey(),
    title: t.string(),
    description: t.string(),
    severity: Severity,
    confidence: Confidence,
    status: IncidentStatus.index('btree'),
    commanderId: t.identity().index('btree'),
    createdAt: t.timestamp().index('btree'),
    updatedAt: t.timestamp().index('btree'),
    version: t.u64(),
    traceId: t.string(),
  }
);

const incidentAccess = table(
  { name: 'incident_access', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    incidentId: t.string().index('btree'),
    userId: t.identity().index('btree'),
    level: IncidentAccessLevel,
    grantedBy: t.identity(),
    grantedAt: t.timestamp(),
  }
);

const evidence = table(
  { name: 'evidence', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    incidentId: t.string().index('btree'),
    source: t.string(),
    observedAt: t.timestamp(),
    storageRef: t.string(),
    sha256: t.string(),
    trustTier: TrustTier,
    traceId: t.string(),
  }
);

const missions = table(
  { name: 'missions', public: false },
  {
    id: t.string().primaryKey(),
    incidentId: t.string().index('btree'),
    deviceId: t.string().index('btree'),
    type: MissionType,
    waypoint: t.string(),
    zoneId: t.string(),
    state: MissionState.index('btree'),
    expiresAt: t.timestamp().index('btree'),
    commandJson: t.string(),
    resultJson: t.option(t.string()),
    createdAt: t.timestamp().index('btree'),
    updatedAt: t.timestamp().index('btree'),
    version: t.u64(),
    traceId: t.string(),
  }
);

const scopeEntries = table(
  { name: 'scope_entries', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    incidentId: t.string().index('btree'),
    assetId: t.string().index('btree'),
    datasetCategory: t.string(),
    impactDimensions: ImpactDimensionList,
    impactStatuses: ImpactStatusList,
    estimatedRecords: t.u64(),
    evidenceRefs: StringList,
    reviewer: t.identity(),
    note: t.string(),
    updatedAt: t.timestamp(),
    version: t.u64(),
  }
);

const actions = table(
  { name: 'actions', public: false },
  {
    id: t.string().primaryKey(),
    incidentId: t.string().index('btree'),
    type: ActionType,
    targetId: t.string().index('btree'),
    initiator: t.identity(),
    approvalId: t.option(t.u64()),
    fingerprint: t.string().unique(),
    state: ActionState.index('btree'),
    reason: t.string(),
    verificationRef: t.option(t.string()),
    createdAt: t.timestamp().index('btree'),
    updatedAt: t.timestamp().index('btree'),
    version: t.u64(),
    traceId: t.string(),
  }
);

const approvals = table(
  { name: 'approvals', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    actorId: t.identity().index('btree'),
    actionId: t.string().index('btree'),
    decision: ApprovalDecision,
    expiresAt: t.timestamp().index('btree'),
    decidedAt: t.timestamp(),
    note: t.string(),
    traceId: t.string(),
  }
);

const outbox = table(
  { name: 'outbox', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    actionId: t.string().unique(),
    incidentId: t.string().index('btree'),
    type: t.string(),
    targetId: t.string(),
    payloadJson: t.string(),
    state: OutboxState.index('btree'),
    attempts: t.u32(),
    claimOwner: t.string(),
    claimedAt: t.timestamp().index('btree'),
    createdAt: t.timestamp().index('btree'),
    resultJson: t.option(t.string()),
    traceId: t.string(),
  }
);

const usersAndRoles = table(
  { name: 'users_and_roles', public: false },
  {
    userId: t.identity().primaryKey(),
    role: UserRole.index('btree'),
    incidentScope: StringList,
    revoked: t.bool(),
    note: t.string(),
    createdAt: t.timestamp().index('btree'),
  }
);

const chatMessages = table(
  { name: 'chat_messages', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    incidentId: t.string().index('btree'),
    sender: t.identity().index('btree'),
    senderRole: t.string(),
    kind: ChatKind,
    body: t.string(),
    refId: t.string(),
    createdAt: t.timestamp().index('btree'),
    clientNonce: t.string().unique(),
    traceId: t.string(),
  }
);

const auditEvents = table(
  { name: 'audit_events', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    actor: t.identity().index('btree'),
    operation: t.string().index('btree'),
    entity: t.string().index('btree'),
    incidentId: t.string().index('btree'),
    beforeHash: t.string(),
    afterHash: t.string(),
    detailJson: t.string(),
    at: t.timestamp().index('btree'),
    traceId: t.string(),
  }
);

const rfFrames = table(
  { name: 'rf_frames', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    receiver: t.string().index('btree'),
    kind: t.string().index('btree'),
    at: t.timestamp().index('btree'),
    artifactRef: t.string(),
    metaJson: t.string(),
  }
);

const health = table(
  { name: 'health', public: false },
  {
    component: t.string().primaryKey(),
    status: DeviceStatus,
    detail: t.string(),
    lastSeen: t.timestamp().index('btree'),
  }
);

const correlationDedupe = table(
  { name: 'correlation_dedupe', public: false },
  {
    key: t.string().primaryKey(),
    alertId: t.u64(),
    incidentId: t.string(),
    createdAt: t.timestamp().index('btree'),
  }
);

export const maintenanceTicks = table(
  { name: 'maintenance_ticks', public: false },
  {
    id: t.u64().primaryKey().autoInc(),
    scheduledAt: t.scheduleAt(),
  }
);

const spacetimedb = schema({
  devices,
  zones,
  assets,
  devicePrincipals,
  observations,
  alerts,
  incidents,
  incidentAccess,
  evidence,
  missions,
  scopeEntries,
  actions,
  approvals,
  outbox,
  usersAndRoles,
  chatMessages,
  auditEvents,
  rfFrames,
  health,
  correlationDedupe,
  maintenanceTicks,
});

export {
  devices, zones, assets, devicePrincipals, observations, alerts, incidents,
  incidentAccess, evidence, missions, scopeEntries, actions, approvals, outbox,
  usersAndRoles, chatMessages, auditEvents, rfFrames, health, correlationDedupe,
};
export default spacetimedb;
