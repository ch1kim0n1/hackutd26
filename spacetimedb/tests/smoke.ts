import { DbConnection } from '../bindings/index';
import { tables, reducers } from '../bindings/index';
import type { Identity } from 'spacetimedb';

// SPACETIMEDB_URI / SPACETIMEDB_DATABASE override the target so the smoke
// suite can run against a scratch database (e.g. `sentinel-hive-smoke`)
// while the seeded `sentinel-hive` lab keeps running. The suite bootstraps
// its own genesis, so it requires a FRESH/EMPTY database.
const URI = process.env.SPACETIMEDB_URI ?? 'ws://127.0.0.1:3000';
const DB = process.env.SPACETIMEDB_DATABASE ?? 'sentinel-hive';

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
// Token cache is per-database: identity tokens are not portable across
// module instances, and each smoke run needs its own genesis anyway.
const TOKENS_FILE = `.smoke-identity-tokens-${DB}.json`;
const savedTokens: Record<string, string> = existsSync(TOKENS_FILE)
  ? JSON.parse(readFileSync(TOKENS_FILE, 'utf8'))
  : {};

function connect(name: string): Promise<{ conn: DbConnection; identity: Identity }> {
  return new Promise((resolve, reject) => {
    let builder = DbConnection.builder().withUri(URI).withDatabaseName(DB);
    if (savedTokens[name]) builder = builder.withToken(savedTokens[name]);
    builder
      .onConnect((conn, identity, token) => {
        savedTokens[name] = token;
        writeFileSync(TOKENS_FILE, JSON.stringify(savedTokens, null, 2));
        resolve({ conn, identity });
      })
      .onConnectError((ctx) => reject(new Error(`connect error ${name}: ${JSON.stringify(ctx)}`)))
      .build();
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
let passed = 0, failed = 0;
function check(name: string, cond: boolean, extra = '') {
  if (cond) { passed++; console.log(`  PASS ${name}`); }
  else { failed++; console.log(`  FAIL ${name} ${extra}`); }
}
async function expectReject(name: string, p: Promise<unknown>) {
  const r = await Promise.race([
    p.then(() => 'resolved' as const).catch(() => 'rejected' as const),
    sleep(3000).then(() => 'timeout' as const),
  ]);
  check(name, r === 'rejected', `got ${r}`);
}

async function main() {
  // ---- connect identities ----
  const { conn: admin, identity: adminId } = await connect('admin');
  const { conn: device, identity: deviceId } = await connect('device-puck');
  const { conn: gateway, identity: gatewayId } = await connect('gateway');
  const { conn: commander, identity: commanderId } = await connect('commander');
  const { conn: responder, identity: responderId } = await connect('responder');
  const { conn: observer, identity: observerId } = await connect('observer');
  const { conn: executor, identity: executorId } = await connect('executor');
  const { conn: agent, identity: agentId } = await connect('agent');
  console.log('connected:', [adminId, deviceId, commanderId, responderId].map((i) => i.toHexString().slice(0, 8)));

  // ---- bootstrap + roles ----
  await admin.reducers.bootstrapAdmin({ note: 'smoke test genesis' });
  await admin.reducers.upsertUserRole({ userId: deviceId, role: 'device', incidentScope: [], note: 'puck' });
  await admin.reducers.upsertUserRole({ userId: gatewayId, role: 'gateway', incidentScope: [], note: 'collector' });
  await admin.reducers.upsertUserRole({ userId: commanderId, role: 'commander', incidentScope: [], note: 'ic' });
  await admin.reducers.upsertUserRole({ userId: responderId, role: 'responder', incidentScope: [], note: 'ir' });
  await admin.reducers.upsertUserRole({ userId: observerId, role: 'observer', incidentScope: [], note: 'obs' });
  await admin.reducers.upsertUserRole({ userId: executorId, role: 'executor', incidentScope: [], note: 'exec' });
  await admin.reducers.upsertUserRole({ userId: agentId, role: 'agent', incidentScope: [], note: 'nemotron' });
  check('roles seeded', true);

  // ---- registry ----
  await admin.reducers.upsertZone({ id: 'rack-01', name: 'Server Rack A', boundsJson: '{"x":0,"y":0,"w":10,"h":10}', waypoints: ['tag-rack-01', 'tag-rack-02'] });
  await admin.reducers.upsertDevice({ id: 'puck-a-01', type: 'puck_contact', zoneId: 'rack-01', firmware: '0.1.0' });
  await admin.reducers.upsertDevice({ id: 'rover-01', type: 'rover', zoneId: 'rack-01', firmware: '0.1.0' });
  await admin.reducers.upsertDevice({ id: 'puck-wifi-01', type: 'puck_wifi', zoneId: 'rack-01', firmware: '0.1.0' });
  await admin.reducers.upsertAsset({ id: 'srv-01', zoneId: 'rack-01', type: 'server', owner: 'lab', authorizedNetworkIds: ['corp-lan'] });
  await admin.reducers.enrollDevicePrincipal({ deviceId: 'puck-a-01', identity: deviceId });
  check('registry seeded', true);

  // ---- device ingest ----
  const nowMicros = BigInt(Date.now()) * 1000n;
  const obsArgs = {
    eventId: 'evt-1', deviceId: 'puck-a-01', kind: 'contact_open', seq: 1n,
    observedAtMicros: nowMicros, zoneId: 'rack-01',
    dataJson: '{"switch":"reed-1","state":"open"}', trustTier: 'device_asserted', traceId: 't-1',
  };
  await device.reducers.ingestObservation(obsArgs);
  await sleep(400);
  // duplicate event id -> idempotent
  await device.reducers.ingestObservation(obsArgs);
  // stale seq -> reject
  await expectReject('stale seq rejected', device.reducers.ingestObservation({ ...obsArgs, eventId: 'evt-2', seq: 1n }));
  // forged device id -> reject
  await expectReject('forged device_id rejected', device.reducers.ingestObservation({ ...obsArgs, eventId: 'evt-3', deviceId: 'puck-wifi-01', seq: 2n }));
  // unknown kind -> reject
  await expectReject('unknown kind rejected', device.reducers.ingestObservation({ ...obsArgs, eventId: 'evt-4', kind: 'rm_rf', seq: 2n }));
  // oversized -> reject
  await expectReject('oversized rejected', device.reducers.ingestObservation({ ...obsArgs, eventId: 'evt-5', dataJson: 'x'.repeat(9000), seq: 2n }));
  // valid next seq
  await device.reducers.ingestObservation({ ...obsArgs, eventId: 'evt-6', seq: 2n, kind: 'contact_closed', dataJson: '{"switch":"reed-1","state":"closed"}' });
  check('device ingest ok', true);

  // ---- subscriptions: two clients see same live state ----
  let cmdIncidents = 0, resIncidents = 0, cmdChats = 0, resChats = 0;
  const feedA = commander.subscriptionBuilder().subscribe((tb) => tb.incidentFeed.build());
  const feedB = responder.subscriptionBuilder().subscribe((tb) => tb.incidentFeed.build());
  const chatA = commander.subscriptionBuilder().subscribe((tb) => tb.chatFeed.build());
  const chatB = responder.subscriptionBuilder().subscribe((tb) => tb.chatFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.pendingApprovals.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.actionFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.missionFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.scopeFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.opsAlertFeed.build());
  executor.subscriptionBuilder().subscribe((tb) => tb.executorOutbox.build());
  gateway.subscriptionBuilder().subscribe((tb) => tb.pendingMissions.build());
  commander.db.incidentFeed.onInsert(() => cmdIncidents++);
  responder.db.incidentFeed.onInsert(() => resIncidents++);
  commander.db.chatFeed.onInsert(() => cmdChats++);
  responder.db.chatFeed.onInsert(() => resChats++);
  await sleep(800);

  // ---- deterministic correlation (issue #18) ----
  // evt-1 (contact_open) already ingested -> exactly one auto alert + incident.
  const autoIncidentRows = () =>
    [...commander.db.incidentFeed.iter()].filter((i: any) =>
      typeof i.title === 'string' && i.title.includes('Physical perimeter contact')
    );
  check('contact_open auto-created one incident', autoIncidentRows().length === 1,
    `got ${autoIncidentRows().length}`);
  const corrAlerts = [...commander.db.opsAlertFeed.iter()].filter(
    (a: any) => a.ruleId === 'perimeter.contact_open'
  );
  check('correlation alert raised', corrAlerts.length === 1, `got ${corrAlerts.length}`);
  check('alert linked to auto incident', (corrAlerts[0] as any)?.incidentId === (autoIncidentRows()[0] as any)?.id);

  // replay same event + a NEW event in the same 5-min bucket -> still one incident
  await device.reducers.ingestObservation(obsArgs); // exact dup of evt-1
  await device.reducers.ingestObservation({ ...obsArgs, eventId: 'evt-7', seq: 3n });
  await sleep(600);
  check('replay + same-bucket dedupe keeps one incident', autoIncidentRows().length === 1,
    `got ${autoIncidentRows().length}`);
  check('dedupe keeps one correlation alert',
    [...commander.db.opsAlertFeed.iter()].filter((a: any) => a.ruleId === 'perimeter.contact_open').length === 1);

  // wifi-only anomaly -> alert tier, NO incident (docs/08: no exposure claims)
  await device.reducers.ingestObservation({
    ...obsArgs, eventId: 'evt-8', seq: 4n, kind: 'wifi_ap_seen',
    dataJson: '{"ssid":"SENTINEL-CORP","bssid":"02:AA:BB:CC:DD:01","channel":6,"rssi_dbm":-48}',
  });
  await sleep(600);
  check('wifi_ap_seen alert only, no incident',
    [...commander.db.opsAlertFeed.iter()].some((a: any) => a.ruleId === 'rf.ap_seen') &&
    autoIncidentRows().length === 1);

  // ---- incident lifecycle ----
  await commander.reducers.createIncident({
    title: 'Rogue cabinet access', description: 'reed switch opened near rack-01',
    severity: 'high', confidence: 'suspected', traceId: 'inc-trace-1',
  });
  await sleep(500);
  const incs = [...commander.db.incidentFeed.iter()].filter(
    (i: any) => i.title === 'Rogue cabinet access'
  );
  check('commander sees manual incident via view', incs.length === 1, `got ${incs.length}`);
  const inc = incs[0] as any;
  check('responder denied pre-grant (scoped)', (await responder.db.incidentFeed.count()) === 0n);
  const incId = inc.id as string;
  check('observer denied incident (no grant)', (await observer.db.incidentFeed.count()) === 0n);

  // grant responder access
  await commander.reducers.grantIncidentAccess({ incidentId: incId, userId: responderId, level: 'responder' });
  await sleep(400);
  check('responder granted sees incident', (await responder.db.incidentFeed.count()) === 1n);

  // chat: responder posts, commander sees live; observer cannot post
  await responder.reducers.postChatMessage({ incidentId: incId, body: 'On it — checking rack cam', clientNonce: 'nonce-1' });
  await sleep(400);
  check('chat visible to commander', cmdChats >= 1, `cmd=${cmdChats}`);
  check('chat visible to responder', resChats >= 1, `res=${resChats}`);
  // idempotent nonce retry
  await responder.reducers.postChatMessage({ incidentId: incId, body: 'On it — checking rack cam', clientNonce: 'nonce-1' });
  await sleep(300);
  const chatRows = [...(await commander.db.chatFeed.iter())].filter(
    (m: any) => m.body === 'On it — checking rack cam'
  );
  check('nonce dedupe single message', chatRows.length === 1, `got ${chatRows.length}`);
  await expectReject('observer cannot post chat', observer.reducers.postChatMessage({ incidentId: incId, body: 'hi', clientNonce: 'nonce-x' }));

  // ---- action pipeline: propose -> approve -> outbox -> executor -> verify ----
  await responder.reducers.proposeAction({ incidentId: incId, type: 'isolate_endpoint', targetId: 'srv-01', reason: 'suspected rogue AP pivot' });
  await sleep(300);
  const pending = [...(await commander.db.pendingApprovals.iter())];
  check('commander sees pending approval', pending.length === 1, `got ${pending.length}`);
  const actId = (pending[0] as any).id as string;
  // SoD: proposer (responder) cannot approve own action
  await expectReject('SoD: proposer cannot approve', responder.reducers.recordApproval({ actionId: actId, decision: 'approved', expiresAtMicros: 0n, note: '' }));
  // commander approves (commander != initiator responder)
  await commander.reducers.recordApproval({ actionId: actId, decision: 'approved', expiresAtMicros: 0n, note: 'approved for lab' });
  // wait for maintenance tick (5s) to enqueue
  await sleep(7000);
  const exRows = [...(await executor.db.executorOutbox.iter())];
  check('executor sees outbox row', exRows.length === 1, `got ${exRows.length}`);
  const outboxId = (exRows[0] as any).id as bigint;
  await executor.reducers.claimOutbox({ outboxId });
  await executor.reducers.recordExecutorOutcome({ outboxId, outcome: 'succeeded', verificationRef: 'lab-fw-rule-77', resultJson: '{"isolated":true}' });
  await commander.reducers.verifyContainment({ actionId: actId, verified: true, note: 'verified isolation' });
  await sleep(400);
  const acts = [...(await commander.db.actionFeed.iter())];
  check('action verified', (acts[0] as any).state.tag.toLowerCase() === 'verified', JSON.stringify((acts[0] as any).state));

  // ---- mission flow ----
  await commander.reducers.assignMission({
    incidentId: incId, deviceId: 'rover-01', type: 'inspect_zone', waypoint: 'tag-rack-01',
    zoneId: 'rack-01', expiresAtMicros: nowMicros + 300_000_000n, maxSpeedMps: 0.25, traceId: 'm-1',
  });
  await sleep(7000); // tick -> missions stay approved; gateway marks dispatched
  const pm = [...(await (gateway as any).db.pendingMissions.iter())];
  check('gateway sees pending mission', pm.length === 1, `got ${pm.length}`);
  const misId = (pm[0] as any).id as string;
  await gateway.reducers.markMissionDispatched({ missionId: misId });
  await sleep(500);
  // device missions view is for enrolled device principals; rover not enrolled -> use gateway path skip
  // enroll rover quickly? use existing device identity is puck. enroll second principal not possible same identity.
  // Instead verify mission row via commander missionFeed
  const mrows = [...(await commander.db.missionFeed.iter())];
  check('mission dispatched', (mrows[0] as any).state.tag.toLowerCase() === 'dispatched');

  // ---- mission_status telemetry -> mission state machine ----
  // Rover cannot hold a device principal; its state events arrive through
  // gateway ingest as mission_status observations. Each must advance the
  // mission row (mirrors recordMissionResult legality); out-of-order and
  // foreign-device statuses are skipped, never thrown.
  const ms = async (ev: string, seq: bigint, state: string, dev = 'rover-01') =>
    gateway.reducers.ingestObservation({
      eventId: ev, deviceId: dev, kind: 'mission_status', seq,
      observedAtMicros: nowMicros, zoneId: 'rack-01',
      dataJson: JSON.stringify({ mission_id: misId, command_id: misId, state, reason: '' }),
      trustTier: 'gateway_validated', traceId: `ms-${ev}`,
    });
  const missionTag = async () => {
    const rows = [...(await commander.db.missionFeed.iter())];
    return String((rows[0] as any).state.tag).toLowerCase();
  };
  await ms('evt-ms-1', 20n, 'accepted');
  await sleep(300);
  check('mission_status accepted advances mission', (await missionTag()) === 'accepted');
  await ms('evt-ms-2', 21n, 'navigating');
  await sleep(300);
  check('mission_status navigating advances mission', (await missionTag()) === 'navigating');
  // replay terminal: completed advances; duplicate event no-ops via eventId
  await ms('evt-ms-3', 22n, 'completed');
  await sleep(300);
  check('mission_status completed advances mission', (await missionTag()) === 'completed');
  await gateway.reducers.ingestObservation({
    eventId: 'evt-ms-3', deviceId: 'rover-01', kind: 'mission_status', seq: 23n,
    observedAtMicros: nowMicros, zoneId: 'rack-01',
    dataJson: JSON.stringify({ mission_id: misId, state: 'failed' }),
    trustTier: 'gateway_validated', traceId: 'ms-dup',
  });
  await sleep(300);
  check('duplicate mission_status event is no-op', (await missionTag()) === 'completed');
  // foreign device must not move rover's mission
  await ms('evt-ms-4', 24n, 'failed', 'puck-a-01');
  await sleep(300);
  check('foreign-device status ignored', (await missionTag()) === 'completed');

  // ---- agent propose -> commander approve (GLUE-03 SoD) ----
  await commander.reducers.grantIncidentAccess({ incidentId: incId, userId: agentId, level: 'responder' });
  await sleep(400);
  await agent.reducers.proposeMission({
    incidentId: incId, deviceId: 'rover-01', type: 'capture_photo',
    waypoint: 'tag-rack-01', zoneId: 'rack-01',
    expiresAtMicros: nowMicros + 300_000_000n, maxSpeedMps: 0.2,
    justification: 'cabinet event needs photo evidence', traceId: 'p-1',
  });
  await sleep(500);
  const pms = [...(await commander.db.missionFeed.iter())];
  const proposed = pms.find((m: any) => String(m.state.tag).toLowerCase() === 'proposed') as any;
  check('agent mission lands in proposed', !!proposed);
  check('proposed not in gateway downlink',
    [...(await (gateway as any).db.pendingMissions.iter())].every((m: any) => m.id !== proposed?.id));
  // SoD: the proposing agent cannot approve; observers cannot approve.
  await expectReject('agent cannot approve own proposal',
    agent.reducers.approveMission({ missionId: proposed.id }));
  await expectReject('observer cannot approve mission',
    observer.reducers.approveMission({ missionId: proposed.id }));
  await commander.reducers.approveMission({ missionId: proposed.id });
  await sleep(400);
  check('commander approves -> approved + visible to gateway',
    [...(await (gateway as any).db.pendingMissions.iter())].some((m: any) => m.id === proposed.id));
  // non-agent cannot propose; puck targets rejected
  await expectReject('commander cannot use proposeMission',
    commander.reducers.proposeMission({
      incidentId: incId, deviceId: 'rover-01', type: 'patrol',
      waypoint: 'tag-rack-01', zoneId: 'rack-01',
      expiresAtMicros: nowMicros + 300_000_000n, maxSpeedMps: 0.2,
      justification: 'x', traceId: 'p-2',
    }));

  // ---- scope ----
  await responder.reducers.updateScope({
    incidentId: incId, assetId: 'srv-01', datasetCategory: 'customer_records',
    impactDimensions: ['confidentiality'], impactStatuses: ['suspected_exposed'],
    estimatedRecords: 0n, evidenceRefs: [], note: 'rogue AP near rack; data impact unknown',
    expectedVersion: 0n,
  });
  await sleep(300);
  const scopes = [...(await commander.db.scopeFeed.iter())];
  check('scope entry created', scopes.length === 1);
  check('scope status suspected not confirmed', (scopes[0] as any).impactStatuses[0].tag.toLowerCase().replace(/_/g,'') === 'suspectedexposed');

  // ---- data-center node telemetry (virtual Pi fleet, apps/datacenter) ----
  // Same canonical envelope as physical agents; correlation is data-aware.
  await admin.reducers.upsertZone({ id: 'lab-b', name: 'Network Lab B', boundsJson: '{}', waypoints: [] });
  await admin.reducers.upsertZone({ id: 'bench-row', name: 'Bench Row', boundsJson: '{}', waypoints: [] });
  for (const [did, zone] of [
    ['vpi-compute-01', 'rack-01'], ['vpi-network-01', 'lab-b'],
    ['vpi-sensor-01', 'rack-01'], ['vpi-mgmt-01', 'bench-row'],
  ] as const) {
    await admin.reducers.upsertDevice({ id: did, type: 'other', zoneId: zone, firmware: 'vpi-sim-0.1' });
  }
  commander.subscriptionBuilder().subscribe((tb) => tb.deviceFeed.build());
  await sleep(400);

  const dcAlerts = () =>
    [...commander.db.opsAlertFeed.iter()].filter((a: any) =>
      String(a.ruleId).startsWith('node.') || String(a.ruleId).startsWith('dc.'));
  let dcSeq = 100n;
  const dcIngest = (deviceId: string, zoneId: string, kind: string,
                    data: unknown, observedMicros: bigint = nowMicros) =>
    gateway.reducers.ingestObservation({
      eventId: `evt-dc-${deviceId}-${dcSeq}`, deviceId, kind, seq: dcSeq++,
      observedAtMicros: observedMicros, zoneId,
      dataJson: JSON.stringify(data), trustTier: 'gateway_validated',
      traceId: `dc-${deviceId}`,
    });

  // benign telemetry: ok heartbeat, high CPU metric, ordinary flow -> nothing
  await dcIngest('vpi-compute-01', 'rack-01', 'device_health',
    { status: 'ok', note: 'heartbeat', uptime_s: 60 });
  await dcIngest('vpi-compute-01', 'rack-01', 'resource_metric',
    { cpu_pct: 99.0, mem_pct: 81.0, load1: 8.2, interval_s: 10 });
  await dcIngest('vpi-network-01', 'lab-b', 'network_flow',
    { src: '192.0.2.10', dst: '192.0.2.102', proto: 'tcp', dst_port: 9100,
      packets: 20, bytes: 4000, duration_s: 0.5, direction: 'ingress' });
  await sleep(600);
  check('benign dc telemetry raises no alerts', dcAlerts().length === 0,
    `got ${dcAlerts().length}`);

  // node fault -> high-severity auto incident
  await dcIngest('vpi-sensor-01', 'rack-01', 'device_health',
    { status: 'fault', note: 'simulated power loss' });
  await sleep(600);
  const faultAlerts = dcAlerts().filter((a: any) => a.ruleId === 'node.health_fault');
  check('node fault -> one alert', faultAlerts.length === 1, `got ${faultAlerts.length}`);
  const faultIncId = (faultAlerts[0] as any)?.incidentId as string;
  check('node fault -> linked auto incident', typeof faultIncId === 'string' && faultIncId.length > 0);
  const faultInc = [...commander.db.incidentFeed.iter()].find((i: any) => i.id === faultIncId) as any;
  check('fault incident in commander feed',
    !!faultInc && String(faultInc.status.tag).toLowerCase() === 'new');
  // device record reflects reported status
  const devRow = [...commander.db.deviceFeed.iter()].find((d: any) => d.id === 'vpi-sensor-01') as any;
  check('device status fault reflected',
    String(devRow?.status?.tag).toLowerCase() === 'fault', JSON.stringify(devRow?.status));

  // same 5-min bucket repeat -> deduped, still one incident
  await dcIngest('vpi-sensor-01', 'rack-01', 'device_health',
    { status: 'fault', note: 'simulated power loss' });
  await sleep(500);
  check('same-bucket fault deduped',
    dcAlerts().filter((a: any) => a.ruleId === 'node.health_fault').length === 1);
  // different bucket (observed 6min earlier) -> new incident allowed
  await dcIngest('vpi-sensor-01', 'rack-01', 'device_health',
    { status: 'fault', note: 'simulated power loss' }, nowMicros - 360_000_000n);
  await sleep(500);
  check('new-bucket fault -> second incident',
    dcAlerts().filter((a: any) => a.ruleId === 'node.health_fault').length === 2);

  // degraded -> alert only, no incident
  await dcIngest('vpi-mgmt-01', 'bench-row', 'device_health',
    { status: 'degraded', note: 'config drift: ssh_password_auth' });
  await sleep(500);
  const degAlerts = dcAlerts().filter((a: any) => a.ruleId === 'node.health_degraded');
  check('degraded -> alert, no incident',
    degAlerts.length === 1 && !(degAlerts[0] as any).incidentId,
    `got ${degAlerts.length} alerts`);

  // unexpected service listener -> incident; clean inventory -> resolves
  await dcIngest('vpi-compute-01', 'rack-01', 'service_inventory',
    { listeners: [{ name: 'sshd', port: 22, proto: 'tcp', expected: true },
                  { name: 'minerd', port: 3333, proto: 'tcp', expected: false }],
      unexpected: [{ name: 'minerd', port: 3333, proto: 'tcp' }] });
  await sleep(500);
  const svcAlerts = dcAlerts().filter((a: any) => a.ruleId === 'dc.unexpected_service');
  check('unexpected service -> incident',
    svcAlerts.length === 1 && !!(svcAlerts[0] as any).incidentId);
  await dcIngest('vpi-compute-01', 'rack-01', 'service_inventory',
    { listeners: [{ name: 'sshd', port: 22, proto: 'tcp', expected: true }],
      unexpected: [] });
  await sleep(500);
  const svcAfter = dcAlerts().filter((a: any) => a.ruleId === 'dc.unexpected_service');
  check('clean inventory resolves service alert',
    svcAfter.length === 1 && String((svcAfter[0] as any).state.tag).toLowerCase() === 'resolved',
    JSON.stringify((svcAfter[0] as any)?.state));

  // config drift -> incident; resolved drift -> clears the alert
  await dcIngest('vpi-mgmt-01', 'bench-row', 'config_drift',
    { key: 'ssh_password_auth', baseline: false, live: true, resolved: false });
  await sleep(500);
  const driftAlerts = dcAlerts().filter((a: any) => a.ruleId === 'dc.config_drift');
  check('config drift -> incident',
    driftAlerts.length === 1 && !!(driftAlerts[0] as any).incidentId);
  await dcIngest('vpi-mgmt-01', 'bench-row', 'config_drift',
    { key: 'ssh_password_auth', baseline: false, live: false, resolved: true });
  await sleep(500);
  const driftAfter = dcAlerts().filter((a: any) => a.ruleId === 'dc.config_drift');
  check('resolved drift clears alert',
    String((driftAfter[0] as any)?.state.tag).toLowerCase() === 'resolved');

  // suspicious flow (scan summary) -> incident; egress bulk flow too
  await dcIngest('vpi-sensor-01', 'rack-01', 'network_flow',
    { src: '198.51.100.66', dst: '192.0.2.101', proto: 'tcp',
      distinct_dst_ports: 32, packets: 1280, bytes: 51200,
      duration_s: 4.2, direction: 'ingress' });
  await sleep(500);
  const flowAlerts = dcAlerts().filter((a: any) => a.ruleId === 'dc.suspicious_flow');
  check('suspicious flow -> incident',
    flowAlerts.length === 1 && !!(flowAlerts[0] as any).incidentId);

  // recovery: drive incident to 'contained' (only legal source of 'recovery'),
  // then recovered heartbeat resolves alerts and moves it to recovery.
  await commander.reducers.setIncidentStatus({ incidentId: faultIncId, status: 'triage', expectedVersion: 1n, note: 'ack' });
  await commander.reducers.setIncidentStatus({ incidentId: faultIncId, status: 'investigating', expectedVersion: 2n, note: 'triage done' });
  await commander.reducers.setIncidentStatus({ incidentId: faultIncId, status: 'containment_pending', expectedVersion: 3n, note: 'isolating node' });
  await commander.reducers.setIncidentStatus({ incidentId: faultIncId, status: 'contained', expectedVersion: 4n, note: 'node isolated' });
  await dcIngest('vpi-sensor-01', 'rack-01', 'device_health',
    { status: 'ok', note: 'recovered', recovered: true });
  await sleep(600);
  const faultAlertsAfter = dcAlerts().filter((a: any) => a.ruleId === 'node.health_fault');
  check('recovery resolves fault alerts',
    faultAlertsAfter.every((a: any) => String(a.state.tag).toLowerCase() === 'resolved'),
    JSON.stringify(faultAlertsAfter.map((a: any) => a.state)));
  const recInc = [...commander.db.incidentFeed.iter()].find((i: any) => i.id === faultIncId) as any;
  check('incident moved to recovery',
    String(recInc?.status.tag).toLowerCase() === 'recovery', String(recInc?.status.tag));
  const devOk = [...commander.db.deviceFeed.iter()].find((d: any) => d.id === 'vpi-sensor-01') as any;
  check('device status back online',
    String(devOk?.status?.tag).toLowerCase() === 'online', JSON.stringify(devOk?.status));

  // ---- RBAC negatives ----
  await expectReject('device cannot create incident', device.reducers.createIncident({ title: 'x', description: 'x', severity: 'low', confidence: 'unknown', traceId: 'x' }));
  await expectReject('observer cannot create incident', observer.reducers.createIncident({ title: 'x', description: 'x', severity: 'low', confidence: 'unknown', traceId: 'x' }));
  await expectReject('responder cannot set status', responder.reducers.setIncidentStatus({ incidentId: incId, status: 'investigating', expectedVersion: 1n, note: 'x' }));
  await commander.reducers.setIncidentStatus({ incidentId: incId, status: 'triage', expectedVersion: 1n, note: 'ack' });
  await commander.reducers.setIncidentStatus({ incidentId: incId, status: 'investigating', expectedVersion: 2n, note: 'triage done' });
  await sleep(300);
  const manualRow = [...commander.db.incidentFeed.iter()].find(
    (i: any) => i.title === 'Rogue cabinet access'
  ) as any;
  check('status transition ok', manualRow?.status?.tag?.toLowerCase() === 'investigating');

  // unsubscribe
  for (const s of [feedA, feedB, chatA, chatB]) s.unsubscribe();
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((e) => { console.error('FATAL', e); process.exit(2); });
