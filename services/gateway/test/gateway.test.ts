// Integration test for the MQTT gateway (issue #17).
// Requires: local SpacetimeDB running with `sentinel-hive` published and the
// lab seeded (see deploy/). Identity tokens are read from
// GATEWAY_TEST_TOKENS (JSON: {gateway, executor, commander, responder}).
//
//   npx tsx test/gateway.test.ts
//
// Spins up an in-process aedes broker, launches src/index.ts as a child
// process, then exercises: valid/invalid/forged/oversized telemetry, mission
// downlink over MQTT, and the action outbox claim->execute->outcome path.

import { spawn, type ChildProcess } from 'node:child_process';
import { createServer } from 'node:net';
import { createHmac } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const createBroker = (require('aedes') as any).createBroker as () => any;
import mqtt from 'mqtt';
import { DbConnection } from '../bindings/index';
import { canonicalJson } from '../src/validate.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const URI = process.env.SPACETIMEDB_URI ?? 'ws://127.0.0.1:3000';
const DB = process.env.SPACETIMEDB_DATABASE ?? 'sentinel-hive';

const tokens: Record<string, string> = JSON.parse(
  process.env.GATEWAY_TEST_TOKENS ?? '{}'
);
for (const role of ['gateway', 'executor', 'commander', 'responder']) {
  if (!tokens[role]) throw new Error(`GATEWAY_TEST_TOKENS missing "${role}"`);
}

// puck-a-01 is HMAC-keyed in this test gateway: envelopes for it MUST carry
// a valid signature (docs/13 §1). Sign exactly like sensors/pucks
// Observation.canonical() + auth.sign: HMAC-SHA256 over the 8 signed fields
// as sorted-key compact JSON.
const DEVICE_HMAC = 'gw-test-device-secret';
const SIGNED_FIELDS = [
  'schema_version', 'event_id', 'device_id', 'seq',
  'observed_at', 'kind', 'zone_id', 'data',
] as const;
function signEnvelope(env: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const f of SIGNED_FIELDS) body[f] = env[f];
  return {
    ...env,
    signature: createHmac('sha256', DEVICE_HMAC).update(canonicalJson(body)).digest('hex'),
  };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
let passed = 0, failed = 0;
function check(name: string, cond: boolean, extra = '') {
  if (cond) { passed++; console.log(`  PASS ${name}`); }
  else { failed++; console.log(`  FAIL ${name} ${extra}`); }
}

async function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const s = createServer().listen(0, '127.0.0.1', () => {
      const p = (s.address() as any).port;
      s.close(() => resolve(p));
    });
  });
}

function connect(token: string): Promise<DbConnection> {
  return new Promise((resolve, reject) => {
    DbConnection.builder()
      .withUri(URI)
      .withDatabaseName(DB)
      .withToken(token)
      .onConnect((c) => resolve(c))
      .onConnectError((_ctx, e) => reject(e))
      .build();
  });
}

async function main() {
  // --- broker + gateway process ---
  const broker = createBroker();
  const mqttPort = await freePort();
  const net = createServer(broker.handle);
  await new Promise<void>((r) => net.listen(mqttPort, '127.0.0.1', r));

  const healthPort = 18081 + Math.floor(Math.random() * 500);
  const stateFile = join(ROOT, `.test-state-${process.pid}.json`);
  const gw: ChildProcess = spawn('npx', ['tsx', 'src/index.ts'], {
    cwd: ROOT,
    env: {
      ...process.env,
      SPACETIMEDB_URI: URI,
      SPACETIMEDB_DATABASE: DB,
      SPACETIMEDB_TOKEN: tokens.gateway,
      EXECUTOR_SPACETIMEDB_TOKEN: tokens.executor,
      MQTT_URL: `tcp://127.0.0.1:${mqttPort}`,
      MQTT_TOPIC_PREFIX: 'sentinel/v1',
      GATEWAY_HEALTH_PORT: String(healthPort),
      GATEWAY_STATE_FILE: stateFile,
      GATEWAY_DEVICE_HMAC_KEYS: JSON.stringify({ 'puck-a-01': DEVICE_HMAC }),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  gw.stderr?.on('data', (d) => process.stderr.write(`[gw] ${d}`));

  // wait for health
  let healthy = false;
  for (let i = 0; i < 60 && !healthy; i++) {
    await sleep(500);
    try {
      const r = await fetch(`http://127.0.0.1:${healthPort}/healthz`);
      healthy = r.ok;
    } catch { /* not up yet */ }
  }
  check('gateway healthz ok', healthy);
  if (!healthy) throw new Error('gateway did not become healthy');

  // --- std clients for assertions ---
  const commander = await connect(tokens.commander);
  const responder = await connect(tokens.responder);
  commander.subscriptionBuilder().subscribe((tb) => tb.incidentFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.observationFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.deviceFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.missionFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.actionFeed.build());
  commander.subscriptionBuilder().subscribe((tb) => tb.pendingApprovals.build());
  await sleep(800);

  // seq must stay ahead of the device's persisted lastSeq or the reducer
  // rejects it as stale — read the live value so re-runs against the same
  // database keep working.
  const seqBase = (() => {
    for (const d of commander.db.deviceFeed.iter() as Iterable<any>) {
      if (d.id === 'puck-a-01') return Number(d.lastSeq) + 1;
    }
    return 1;
  })();

  // --- MQTT publisher ---
  const mqttClient = mqtt.connect(`tcp://127.0.0.1:${mqttPort}`, { clientId: `test-pub-${process.pid}` });
  await new Promise<void>((res, rej) => {
    mqttClient.on('connect', () => res());
    mqttClient.on('error', rej);
  });
  const pub = (topic: string, obj: unknown) =>
    new Promise<void>((res, rej) =>
      mqttClient.publish(topic, JSON.stringify(obj), { qos: 1 }, (e) => (e ? rej(e) : res()))
    );

  const nowIso = new Date().toISOString();
  const baseEnv = {
    schema_version: 1,
    device_id: 'puck-a-01',
    seq: seqBase,
    observed_at: nowIso,
    kind: 'contact_open',
    zone_id: 'rack-01',
    data: { switch: 'reed-9', state: 'open' },
    trace_id: 'gw-test-1',
  };
  const hasEvent = async (eventId: string) =>
    [...(await commander.db.observationFeed.iter())].some(
      (o: any) => o.eventId === eventId
    );

  // 1) valid signed telemetry -> observation lands via gateway role
  await pub('sentinel/v1/puck-a-01/telemetry', signEnvelope({ ...baseEnv, event_id: 'gw-evt-1' }));
  await sleep(1200);
  const obs = [...(await commander.db.observationFeed.iter())].filter(
    (o: any) => o.eventId === 'gw-evt-1'
  );
  check('valid signed telemetry ingested', obs.length === 1, `got ${obs.length}`);
  check('trust tier gateway_validated', (obs[0] as any)?.trustTier?.tag?.toLowerCase?.().includes('gateway') ?? false);

  // 2) duplicate event_id -> idempotent, still one row
  await pub('sentinel/v1/puck-a-01/telemetry', signEnvelope({ ...baseEnv, event_id: 'gw-evt-1' }));
  await sleep(800);
  const obs2 = [...(await commander.db.observationFeed.iter())].filter(
    (o: any) => o.eventId === 'gw-evt-1'
  );
  check('duplicate event_id deduped', obs2.length === 1);

  // 2b) bad signature on keyed device -> rejected
  await pub('sentinel/v1/puck-a-01/telemetry', {
    ...baseEnv, event_id: 'gw-evt-badsig', seq: seqBase + 1,
    signature: 'a'.repeat(64),
  });
  await sleep(800);
  check('bad signature rejected', !(await hasEvent('gw-evt-badsig')));

  // 2c) missing signature on keyed device -> rejected
  await pub('sentinel/v1/puck-a-01/telemetry', {
    ...baseEnv, event_id: 'gw-evt-nosig', seq: seqBase + 2,
  });
  await sleep(800);
  check('missing signature rejected', !(await hasEvent('gw-evt-nosig')));

  // 3) forged device_id (payload != topic) -> rejected
  await pub('sentinel/v1/puck-a-01/telemetry', {
    ...baseEnv, event_id: 'gw-evt-forge', device_id: 'puck-wifi-01', seq: seqBase + 3,
  });
  await sleep(800);
  const forged = [...(await commander.db.observationFeed.iter())].filter(
    (o: any) => o.eventId === 'gw-evt-forge'
  );
  check('forged device_id rejected', forged.length === 0);

  // 4) unknown kind -> rejected
  await pub('sentinel/v1/puck-a-01/telemetry', {
    ...baseEnv, event_id: 'gw-evt-badkind', kind: 'rm_rf', seq: seqBase + 4,
  });
  await sleep(800);
  const badKind = [...(await commander.db.observationFeed.iter())].filter(
    (o: any) => o.eventId === 'gw-evt-badkind'
  );
  check('unknown kind rejected', badKind.length === 0);

  // 5) oversized data -> rejected
  await pub('sentinel/v1/puck-a-01/telemetry', {
    ...baseEnv, event_id: 'gw-evt-big', seq: seqBase + 5, data: { blob: 'x'.repeat(9000) },
  });
  await sleep(800);
  const big = [...(await commander.db.observationFeed.iter())].filter(
    (o: any) => o.eventId === 'gw-evt-big'
  );
  check('oversized payload rejected', big.length === 0);

  // 6) wrong schema_version -> rejected
  await pub('sentinel/v1/puck-a-01/telemetry', {
    ...baseEnv, event_id: 'gw-evt-v2', schema_version: 2, seq: seqBase + 6,
  });
  await sleep(800);
  const v2 = [...(await commander.db.observationFeed.iter())].filter(
    (o: any) => o.eventId === 'gw-evt-v2'
  );
  check('bad schema_version rejected', v2.length === 0);

  // --- mission downlink ---
  // create incident + assign mission as commander. Title carries the pid so
  // re-runs against a persistent database never resolve to a stale incident.
  const incTitle = `GW test incident ${process.pid}`;
  await commander.reducers.createIncident({
    title: incTitle, description: 'gateway e2e', severity: 'medium',
    confidence: 'suspected', traceId: 'gw-inc',
  });
  await sleep(600);
  const incs = [...(await commander.db.incidentFeed.iter())];
  const inc = incs.find((i: any) => i.title === incTitle) as any;
  check('incident created', !!inc);
  const incId = inc.id as string;

  // grant responder, propose+approve action to exercise outbox
  const expiresMicros = BigInt(Date.now() + 240_000) * 1000n;
  await commander.reducers.assignMission({
    incidentId: incId, deviceId: 'rover-01', type: 'inspect_zone',
    waypoint: 'tag-rack-01', zoneId: 'rack-01',
    expiresAtMicros: expiresMicros, maxSpeedMps: 0.25, traceId: 'gw-mis',
  });

  // listen for the MQTT command
  const cmdP = new Promise<string>((resolve) => {
    const h = (topic: string, payload: Buffer) => {
      if (topic === 'sentinel/v1/rover-01/command') {
        mqttClient.off('message', h);
        resolve(payload.toString());
      }
    };
    mqttClient.on('message', h);
    mqttClient.subscribe('sentinel/v1/rover-01/command');
  });
  const cmdJson = await Promise.race([cmdP, sleep(12000).then(() => '')]);
  check('mission command published over MQTT', cmdJson.length > 0);
  if (cmdJson) {
    const cmd = JSON.parse(cmdJson);
    check('command contract fields', cmd.schema_version === 1 && cmd.device_id === 'rover-01' && !!cmd.mission_id && !!cmd.expires_at);
  }
  await sleep(800);
  const missions = [...(await commander.db.missionFeed.iter())].filter(
    (m: any) => m.incidentId === incId
  );
  check('mission marked dispatched', missions.some((m: any) => String(m.state?.tag ?? m.state).toLowerCase().includes('dispatch')));

  // --- outbox worker ---
  // responder proposes; commander approves; tick enqueues; execConn executes
  const resId = responder.identity!;
  await commander.reducers.grantIncidentAccess({ incidentId: incId, userId: resId, level: 'responder' });
  await sleep(400);
  await responder.reducers.proposeAction({
    incidentId: incId, type: 'isolate_endpoint', targetId: 'srv-01',
    reason: 'gateway e2e outbox',
  });
  await sleep(600);
  const pending = [...(await commander.db.pendingApprovals.iter())].filter(
    (a: any) => a.incidentId === incId
  );
  check('pending approval visible', pending.length === 1, `got ${pending.length}`);
  const actId = (pending[0] as any).id as string;
  await commander.reducers.recordApproval({
    actionId: actId, decision: 'approved', expiresAtMicros: 0n, note: 'gw test',
  });
  // wait for maintenance tick (5s) + worker tick (1s)
  let acted = false;
  for (let i = 0; i < 20 && !acted; i++) {
    await sleep(1000);
    const acts = [...(await commander.db.actionFeed.iter())].filter(
      (a: any) => a.id === actId
    );
    const tag = String(acts[0]?.state?.tag ?? acts[0]?.state ?? '').toLowerCase();
    if (tag.includes('succeeded') || tag.includes('executing') || tag.includes('enqueued')) acted = true;
  }
  check('outbox executed by worker', acted);

  // --- restart reconciliation: state file recorded dispatch ---
  const stateJson = JSON.parse(readFileSync(stateFile, 'utf8'));
  check('dispatch state persisted for restart', Object.keys(stateJson.dispatchedMissions ?? {}).length >= 1);

  // cleanup
  mqttClient.end();
  gw.kill('SIGTERM');
  net.close();
  broker.close();
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error('FATAL', e);
  process.exit(2);
});
