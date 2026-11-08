// Foundation end-to-end check (issue #99).
//
//   synthetic observation --MQTT--> gateway --ingestObservation--> SpacetimeDB
//   commander createIncident --> incidentFeed (the view Phantom Command
//   subscribes to) --> read-after-refresh dedupe check
//   + optional Python API facade leg (/healthz agent_provider, login,
//     POST /incidents, POST /investigations)
//
// Prints PASS/FAIL/SKIP per leg and writes a JSON evidence packet to
// deploy/evidence/e2e-<utc>/result.json. Exit code = number of FAIL legs.
//
// Prerequisites (see deploy/README.md + docs/15-DEVELOPER-RUNBOOK.md):
//   docker compose stack up, module published, lab seeded, gateway running,
//   `npm run generate` bindings present in services/gateway.
//
//   cd services/gateway && npx tsx scripts/e2e-foundation.ts
//
// Env overrides: SPACETIMEDB_URI, SPACETIMEDB_DATABASE, E2E_IDENTITIES,
//   E2E_GATEWAY_ENV, E2E_API_BASE, E2E_GATEWAY_HEALTH.
// Secrets are read from gitignored deploy/ files at runtime and are never
// printed or written to the evidence packet.

import { createHmac } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import mqtt from 'mqtt';
import { DbConnection } from '../bindings/index';
import { canonicalJson } from '../src/validate.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const GATEWAY_ROOT = join(HERE, '..');
const REPO_ROOT = join(GATEWAY_ROOT, '..', '..');

const URI = process.env.SPACETIMEDB_URI ?? 'ws://127.0.0.1:3000';
const DB = process.env.SPACETIMEDB_DATABASE ?? 'sentinel-hive';
const IDENTITIES_PATH =
  process.env.E2E_IDENTITIES ?? join(REPO_ROOT, 'deploy', 'secrets', 'identities.json');
const GATEWAY_ENV_PATH =
  process.env.E2E_GATEWAY_ENV ?? join(REPO_ROOT, 'deploy', 'env', 'gateway.env');
const API_BASE = process.env.E2E_API_BASE ?? 'http://127.0.0.1:8000';
const GW_HEALTH = process.env.E2E_GATEWAY_HEALTH ?? 'http://127.0.0.1:8081/healthz';
const EVIDENCE_DIR = join(
  REPO_ROOT, 'deploy', 'evidence',
  `e2e-${new Date().toISOString().replace(/[:.]/g, '-')}`);

// ---------------------------------------------------------------------------

type Leg = { name: string; status: 'PASS' | 'FAIL' | 'SKIP'; detail: string; ms: number };
const legs: Leg[] = [];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function leg(name: string, fn: () => Promise<string>): Promise<void> {
  const t0 = Date.now();
  try {
    const detail = await fn();
    legs.push({ name, status: 'PASS', detail, ms: Date.now() - t0 });
    console.log(`  PASS ${name} — ${detail}`);
  } catch (e) {
    legs.push({ name, status: 'FAIL', detail: String(e).slice(0, 300), ms: Date.now() - t0 });
    console.log(`  FAIL ${name} — ${String(e).slice(0, 200)}`);
  }
}
function skip(name: string, why: string): void {
  legs.push({ name, status: 'SKIP', detail: why, ms: 0 });
  console.log(`  SKIP ${name} — ${why}`);
}

function loadEnvFile(path: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!existsSync(path)) return out;
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$/);
    if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
  return out;
}

const VIEWS = ['deviceFeed', 'observationFeed', 'incidentFeed'] as const;

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

/** Views only populate after an explicit subscription (same path the
 * dashboard's live adapter uses). */
function subscribe(conn: DbConnection): Promise<void> {
  return new Promise((resolve, reject) => {
    conn.subscriptionBuilder()
      .onApplied(() => resolve())
      .onError((_ctx, e) => reject(e))
      .subscribe((tables) =>
        VIEWS.map((v) => (tables as Record<string, { build(): unknown }>)[v].build() as never));
  });
}

async function poll<T>(fn: () => Promise<T | null>, timeoutMs: number, stepMs = 400): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const v = await fn();
    if (v !== null) return v;
    if (Date.now() > deadline) throw new Error(`timed out after ${timeoutMs}ms`);
    await sleep(stepMs);
  }
}

// HMAC-signed canonical envelope — same 8 fields + canonicalJson as
// sensors/pucks Observation.canonical() (see gateway.test.ts).
const SIGNED_FIELDS = [
  'schema_version', 'event_id', 'device_id', 'seq',
  'observed_at', 'kind', 'zone_id', 'data',
] as const;
function signEnvelope(env: Record<string, unknown>, secret: string): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const f of SIGNED_FIELDS) body[f] = env[f];
  return {
    ...env,
    signature: createHmac('sha256', secret).update(canonicalJson(body)).digest('hex'),
  };
}

async function main(): Promise<number> {
  console.log(`foundation e2e — ${new Date().toISOString()}`);
  console.log(`  spacetimedb=${URI} db=${DB} api=${API_BASE}`);

  // ---- preflight ---------------------------------------------------------
  let identities: Record<string, Record<string, string>> = {};
  let gwEnv: Record<string, string> = {};
  let commander: DbConnection | null = null;
  let refresher: DbConnection | null = null;

  await leg('preflight.spacetimedb', async () => {
    const r = await fetch(`${URI.replace('ws', 'http')}/v1/ping`);
    if (!r.ok) throw new Error(`ping ${r.status}`);
    return 'ping ok';
  });

  await leg('preflight.secrets-present', async () => {
    if (!existsSync(IDENTITIES_PATH)) throw new Error(`missing ${IDENTITIES_PATH} — run deploy/scripts/bootstrap.sh`);
    identities = JSON.parse(readFileSync(IDENTITIES_PATH, 'utf8'));
    const ws = identities[URI] ?? identities[Object.keys(identities)[0]];
    if (!ws?.commander) throw new Error('identities.json has no commander token');
    gwEnv = loadEnvFile(GATEWAY_ENV_PATH);
    return `roles=${Object.keys(ws).length}`;
  });

  await leg('preflight.gateway-health', async () => {
    const r = await fetch(GW_HEALTH);
    if (!r.ok) throw new Error(`healthz ${r.status} — is the gateway running?`);
    const j: any = await r.json();
    if (!j.mqttConnected || !j.stdConnected) throw new Error(`gateway degraded: ${JSON.stringify(j.stats ?? {})}`);
    return `ingested=${j.stats?.ingested} uptime=${j.uptimeSec}s`;
  });

  const wsTokens = identities[URI] ?? identities[Object.keys(identities)[0]] ?? {};
  try {
    commander = await connect(wsTokens.commander);
    refresher = await connect(wsTokens.commander);
    await Promise.all([subscribe(commander), subscribe(refresher)]);
  } catch (e) {
    legs.push({ name: 'preflight.sdk-connect', status: 'FAIL', detail: String(e).slice(0, 200), ms: 0 });
    console.log(`  FAIL preflight.sdk-connect — ${String(e).slice(0, 160)}`);
    return finish(1);
  }
  legs.push({ name: 'preflight.sdk-connect', status: 'PASS', detail: 'commander connected + views subscribed', ms: 0 });
  console.log('  PASS preflight.sdk-connect — commander connected + views subscribed');

  // ---- leg 1: synthetic observation -> gateway path -> observationFeed ---
  const stamp = Date.now().toString(36);
  const eventId = `e2e-fdn-${stamp}`;
  const hmacKeys: Record<string, string> = gwEnv.GATEWAY_DEVICE_HMAC_KEYS
    ? JSON.parse(gwEnv.GATEWAY_DEVICE_HMAC_KEYS) : {};
  const deviceId = Object.keys(hmacKeys)[0] ?? 'puck-a-01';
  const mqttEnv = loadEnvFile(join(REPO_ROOT, 'deploy', 'env', 'mqtt.env'));
  // Per-device MQTT passwords live in deploy/env/mqtt.env (gitignored,
  // produced by bootstrap.sh). The ACL only lets device-<id> publish its
  // own telemetry topic — the gateway account cannot.
  const deviceUser = `device-${deviceId}`;
  const devicePass = mqttEnv[`DEVICE_${deviceId.replace(/-/g, '_').toUpperCase()}_PASSWORD`]
    ?? mqttEnv[`${deviceUser.replace(/-/g, '_').toUpperCase()}_PASSWORD`];

  const lastSeqOf = async (): Promise<bigint> => {
    const devices = [...(await commander!.db.deviceFeed.iter())] as any[];
    const dev = devices.find((d) => d.id === deviceId || d.deviceId === deviceId);
    return BigInt(dev?.lastSeq ?? dev?.last_seq ?? 0);
  };

  const publishMqtt = async (seq: bigint): Promise<void> => {
    const env: Record<string, unknown> = {
      schema_version: 1,
      event_id: eventId,
      device_id: deviceId,
      seq: Number(seq),
      observed_at: new Date().toISOString(),
      kind: 'contact_open',
      zone_id: 'rack-01',
      data: { switch: 'reed-e2e', state: 'open', probe: 'foundation-e2e' },
      trace_id: `e2e-${stamp}`,
    };
    const payload = hmacKeys[deviceId]
      ? signEnvelope(env, hmacKeys[deviceId])
      : env;
    const client = mqtt.connect(gwEnv.MQTT_URL ?? 'tcp://127.0.0.1:1883', {
      username: deviceUser,
      password: devicePass,
      clientId: `e2e-fdn-${stamp}`,
      reconnectPeriod: 0,
    });
    try {
      await new Promise<void>((res, rej) => {
        client.once('connect', () => res());
        client.once('error', rej);
        setTimeout(() => rej(new Error('mqtt connect timeout')), 5000);
      });
      await new Promise<void>((res, rej) =>
        client.publish(`${gwEnv.MQTT_TOPIC_PREFIX ?? 'sentinel/v1'}/${deviceId}/telemetry`,
          JSON.stringify(payload), { qos: 1 }, (e) => (e ? rej(e) : res())));
    } finally {
      client.end(true);
    }
  };

  const awaitObservation = () => poll(async () => {
    for (const o of (await commander!.db.observationFeed.iter()) as any[]) {
      if (o.eventId === eventId) return o;
    }
    return null;
  }, 15000);

  if (devicePass) {
    await leg('observation.mqtt-gateway', async () => {
      await publishMqtt(await lastSeqOf() + 1n);
      await awaitObservation();
      return `event ${eventId} via MQTT -> gateway -> observationFeed (device=${deviceId})`;
    });
  } else {
    // No device MQTT credentials provisioned — exercise the same reducer the
    // gateway calls, with the gateway identity. Labelled honestly: this
    // proves persistence+view, NOT the MQTT transport leg.
    await leg('observation.ingest-reducer', async () => {
      const gw = await connect(wsTokens.gateway);
      try {
        await gw.reducers.ingestObservation({
          eventId, deviceId, kind: 'contact_open',
          seq: await lastSeqOf() + 1n,
          observedAtMicros: BigInt(Date.now()) * 1000n,
          zoneId: 'rack-01',
          dataJson: JSON.stringify({ switch: 'reed-e2e', state: 'open', probe: 'foundation-e2e' }),
          trustTier: 'gateway_validated',
          traceId: `e2e-${stamp}`,
        });
      } finally {
        gw.disconnect();
      }
      await awaitObservation();
      return `event ${eventId} via ingestObservation reducer (device=${deviceId}); MQTT leg needs deploy/env/mqtt.env`;
    });
  }

  // ---- leg 2: incident -> incidentFeed -> read-after-refresh ------------
  const incidentTitle = `E2E-FDN-${stamp}`;
  let incidentId = '';
  await leg('incident.create-and-read', async () => {
    await commander!.reducers.createIncident({
      title: incidentTitle,
      description: 'Foundation e2e synthetic incident — safe to close.',
      severity: 'low',
      confidence: 'suspected',
      traceId: `e2e-${stamp}`,
    });
    const row: any = await poll(async () => {
      for (const i of (await commander!.db.incidentFeed.iter()) as any[]) {
        if (i.title === incidentTitle) return i;
      }
      return null;
    }, 15000);
    incidentId = row.id ?? row.incidentId;
    return `incident ${incidentId} in incidentFeed`;
  });

  await leg('incident.read-after-refresh', async () => {
    if (!incidentId) throw new Error('no incident id from previous leg');
    await sleep(800);
    // read-after-refresh: a second connection re-subscribes the same views —
    // the row must appear exactly once (no duplication on resync).
    const matches = [...(await refresher!.db.incidentFeed.iter()) as any[]]
      .filter((i) => i.id === incidentId || i.incidentId === incidentId);
    if (matches.length !== 1) throw new Error(`expected exactly 1 row, got ${matches.length}`);
    const obsMatches = [...(await refresher!.db.observationFeed.iter()) as any[]]
      .filter((o) => o.eventId === eventId);
    return `stable single row; linked observation present=${obsMatches.length === 1}`;
  });

  // ---- leg 3: Python API facade ------------------------------------------
  const apiUp = await (async () => {
    try {
      const r = await fetch(`${API_BASE}/healthz`, { signal: AbortSignal.timeout(2000) });
      return r.ok;
    } catch { return false; }
  })();
  if (!apiUp) {
    skip('api.facade', `no API at ${API_BASE} — start apps/api (uvicorn) to include this leg`);
  } else {
    await leg('api.facade', async () => {
      const hz = await (await fetch(`${API_BASE}/healthz`)).json() as any;
      const provider = hz?.agent_provider?.mode ?? 'unknown';
      const login = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username: 'commander' }),
      });
      if (!login.ok) throw new Error(`login ${login.status}`);
      const { token } = await login.json() as any;
      const auth = { authorization: `Bearer ${token}`, 'content-type': 'application/json' };
      const inc = await fetch(`${API_BASE}/incidents`, {
        method: 'POST', headers: auth,
        body: JSON.stringify({ title: `E2E-API-${stamp}`, summary: 'foundation e2e probe', severity: 'low', zone_id: 'rack-01' }),
      });
      if (!inc.ok) throw new Error(`create incident ${inc.status}`);
      const incBody = await inc.json() as any;
      const iid = incBody?.incident_id ?? incBody?.data?.id ?? incBody?.data?.incident?.id;
      if (!iid) throw new Error('no incident id in API response');
      const inv = await fetch(`${API_BASE}/investigations`, {
        method: 'POST', headers: auth,
        body: JSON.stringify({ incident_id: iid, brief: 'foundation e2e smoke' }),
      });
      if (!inv.ok) throw new Error(`investigation ${inv.status}`);
      const invBody = await inv.json() as any;
      const summary = invBody?.summary ?? invBody?.assessment?.summary ?? invBody?.data?.summary ?? '';
      if (!summary) throw new Error('empty assessment summary');
      return `provider=${provider} incident=${iid} assessment=${summary.length}ch`;
    });
  }

  commander?.disconnect();
  refresher?.disconnect();
  return finish(legs.filter((l) => l.status === 'FAIL').length);
}

function finish(failures: number): number {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const packet = {
    generated_at: new Date().toISOString(),
    spacetimedb: URI, database: DB,
    legs,
    pass: legs.filter((l) => l.status === 'PASS').length,
    fail: legs.filter((l) => l.status === 'FAIL').length,
    skip: legs.filter((l) => l.status === 'SKIP').length,
    note: 'No secrets, tokens, or key material are recorded here.',
  };
  const path = join(EVIDENCE_DIR, 'result.json');
  writeFileSync(path, JSON.stringify(packet, null, 2));
  console.log(`\n${packet.pass} PASS / ${packet.fail} FAIL / ${packet.skip} SKIP`);
  console.log(`evidence: ${path}`);
  return failures;
}

main().then(
  (code) => process.exit(code),
  (e) => { console.error('e2e crashed:', e); process.exit(2); },
);
