import { DbConnection } from '../bindings/index';
import { tables, reducers } from '../bindings/index';
import type { Identity } from 'spacetimedb';

const URI = 'ws://127.0.0.1:3000';
const DB = 'sentinel-hive';

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
const TOKENS_FILE = '.smoke-identity-tokens.json';
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
  console.log('connected:', [adminId, deviceId, commanderId, responderId].map((i) => i.toHexString().slice(0, 8)));

  // ---- bootstrap + roles ----
  await admin.reducers.bootstrapAdmin({ note: 'smoke test genesis' });
  await admin.reducers.upsertUserRole({ userId: deviceId, role: 'device', incidentScope: [], note: 'puck' });
  await admin.reducers.upsertUserRole({ userId: gatewayId, role: 'gateway', incidentScope: [], note: 'collector' });
  await admin.reducers.upsertUserRole({ userId: commanderId, role: 'commander', incidentScope: [], note: 'ic' });
  await admin.reducers.upsertUserRole({ userId: responderId, role: 'responder', incidentScope: [], note: 'ir' });
  await admin.reducers.upsertUserRole({ userId: observerId, role: 'observer', incidentScope: [], note: 'obs' });
  await admin.reducers.upsertUserRole({ userId: executorId, role: 'executor', incidentScope: [], note: 'exec' });
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
  executor.subscriptionBuilder().subscribe((tb) => tb.executorOutbox.build());
  gateway.subscriptionBuilder().subscribe((tb) => tb.pendingMissions.build());
  commander.db.incidentFeed.onInsert(() => cmdIncidents++);
  responder.db.incidentFeed.onInsert(() => resIncidents++);
  commander.db.chatFeed.onInsert(() => cmdChats++);
  responder.db.chatFeed.onInsert(() => resChats++);
  await sleep(800);

  // ---- incident lifecycle ----
  await commander.reducers.createIncident({
    title: 'Rogue cabinet access', description: 'reed switch opened near rack-01',
    severity: 'high', confidence: 'suspected', traceId: 'inc-trace-1',
  });
  await sleep(500);
  const incs = [...(await commander.db.incidentFeed.iter())];
  check('commander sees incident via view', incs.length === 1, `got ${incs.length}`);
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

  // ---- RBAC negatives ----
  await expectReject('device cannot create incident', device.reducers.createIncident({ title: 'x', description: 'x', severity: 'low', confidence: 'unknown', traceId: 'x' }));
  await expectReject('observer cannot create incident', observer.reducers.createIncident({ title: 'x', description: 'x', severity: 'low', confidence: 'unknown', traceId: 'x' }));
  await expectReject('responder cannot set status', responder.reducers.setIncidentStatus({ incidentId: incId, status: 'investigating', expectedVersion: 1n, note: 'x' }));
  await commander.reducers.setIncidentStatus({ incidentId: incId, status: 'triage', expectedVersion: 1n, note: 'ack' });
  await commander.reducers.setIncidentStatus({ incidentId: incId, status: 'investigating', expectedVersion: 2n, note: 'triage done' });
  await sleep(300);
  check('status transition ok', ((await commander.db.incidentFeed.iter()).next().value as any).status.tag.toLowerCase() === 'investigating');

  // unsubscribe
  for (const s of [feedA, feedB, chatA, chatB]) s.unsubscribe();
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((e) => { console.error('FATAL', e); process.exit(2); });
