// SENTINEL HIVE lab seed (issue #36).
//
// Creates INDEPENDENTLY AUTHENTICATED demo identities — one SpacetimeDB
// identity + token per role — bootstraps the directory, registers the lab
// registry (zones/devices/assets), and enrolls device principals.
//
// Run against a FRESH database (deploy/scripts/bootstrap.sh does this):
//   cd deploy/seeds && npm install && npm run generate
//   SPACETIMEDB_URI=ws://127.0.0.1:3000 SPACETIMEDB_DATABASE=sentinel-hive \
//     npx tsx seed.ts
//
// Output: ../secrets/identities.json (gitignored) + env snippets on stdout.
// Tokens are credentials — never commit them.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DbConnection } from './bindings/index';
import type { Identity } from 'spacetimedb';

const __dirname = dirname(fileURLToPath(import.meta.url));
const URI = process.env.SPACETIMEDB_URI ?? 'ws://127.0.0.1:3000';
const DB = process.env.SPACETIMEDB_DATABASE ?? 'sentinel-hive';
const TOKENS_FILE = join(__dirname, '..', 'secrets', 'identities.json');
const SECRETS_DIR = join(__dirname, '..', 'secrets');

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Stable identities: reuse saved tokens across runs so re-seeding is
// idempotent and demo logins stay consistent.
// Tokens are server-specific (JWT issuer differs per SpacetimeDB instance),
// so they are stored per-URI: { "<spacetimedb uri>": { "<role>": "<token>" } }.
const allTokens: Record<string, Record<string, string>> = existsSync(TOKENS_FILE)
  ? JSON.parse(readFileSync(TOKENS_FILE, 'utf8'))
  : {};
const saved: Record<string, string> = allTokens[URI] ?? {};

interface Session {
  name: string;
  conn: DbConnection;
  identity: Identity;
}

async function connectOnce(name: string, token: string | undefined) {
  return new Promise<{ conn: DbConnection; identity: Identity; token: string }>(
    (resolve, reject) => {
      let b = DbConnection.builder().withUri(URI).withDatabaseName(DB);
      if (token) b = b.withToken(token);
      b.onConnect((c, id, tok) => resolve({ conn: c, identity: id, token: tok }))
        .onConnectError((_ctx, e) => reject(e))
        .build();
    }
  );
}

async function connect(name: string): Promise<Session> {
  try {
    const r = await connectOnce(name, saved[name]);
    saved[name] = r.token;
    return { name, conn: r.conn, identity: r.identity };
  } catch (e) {
    // Saved token belongs to a different server instance (e.g. compose vs
    // host `spacetime start`) — mint a fresh identity for this server.
    if (saved[name]) {
      delete saved[name];
      const r = await connectOnce(name, undefined);
      saved[name] = r.token;
      return { name, conn: r.conn, identity: r.identity };
    }
    throw e;
  }
}

const roles: Array<[string, string]> = [
  ['admin', 'admin'],
  ['commander', 'commander'],
  ['responder', 'responder'],
  ['observer', 'observer'],
  ['agent', 'agent'],
  ['gateway', 'gateway'],
  ['executor', 'executor'],
];

async function main() {
  const sessions = new Map<string, Session>();
  for (const [name] of roles) sessions.set(name, await connect(name));
  // device identities (enrolled principals, not human roles)
  for (const d of ['puck-a-01', 'rover-01', 'puck-wifi-01', 'kismet-01', 'sdr-01']) {
    sessions.set(`device-${d}`, await connect(`device-${d}`));
  }
  console.log(`connected ${sessions.size} identities`);

  const admin = sessions.get('admin')!;
  const id = (n: string) => sessions.get(n)!.identity;

  // 1) genesis — first run bootstraps admin; later runs skip gracefully
  try {
    await admin.conn.reducers.bootstrapAdmin({ note: 'lab seed genesis' });
    console.log('bootstrapAdmin: seeded');
  } catch (e) {
    if (String(e).includes('already initialized')) {
      console.log('bootstrapAdmin: directory already initialized (idempotent)');
    } else throw e;
  }

  // 2) roles
  for (const [name, role] of roles) {
    await admin.conn.reducers.upsertUserRole({
      userId: id(name),
      role,
      incidentScope: [],
      note: `demo ${role}`,
    });
  }
  console.log('roles: seeded');

  // 3) lab registry — zone ids must cover every emitter: datacenter sim
  // (rack-01/lab-b/bench-row/lobby), rover routes.json
  // (lobby/rack-01/desk-row-a/cabinet-01), pucks (rack-01/lab-bench/
  // cabinet-01), mission-shim waypoints (wp-* rover ids + tag-* ids).
  const ZONES: Array<[string, string, string, string[]]> = [
    ['rack-01', 'Server Rack A', '{"x":0,"y":0,"w":10,"h":10}',
     ['tag-rack-01', 'tag-rack-02', 'tag-door-01',
      'wp-rack-a', 'wp-rack-b', 'wp-cabinet']],
    ['lab-floor', 'Lab Floor', '{"x":0,"y":0,"w":20,"h":20}',
     ['tag-lab-01', 'tag-lab-02', 'wp-desk-1', 'wp-desk-2']],
    ['lab-b', 'Network Lab B', '{"x":-3,"y":-2,"w":3,"d":2}',
     ['tag-lab-b-01', 'wp-desk-1']],
    ['bench-row', 'Engineer Bench Row', '{"x":-1,"y":0,"w":5,"d":1.5}',
     ['wp-desk-1', 'wp-desk-2']],
    ['lobby', 'Lobby and Check-in', '{"x":0,"y":4,"w":4,"d":2}',
     ['wp-home', 'wp-lobby-n']],
    ['cabinet-01', 'Cabinet Row', '{"x":2,"y":3,"w":2,"d":1}',
     ['wp-cabinet', 'tag-door-01']],
    ['desk-row-a', 'Desk Row A', '{"x":0,"y":5,"w":6,"d":2}',
     ['wp-desk-1', 'wp-desk-2']],
    ['lab-bench', 'Lab Bench', '{"x":-2,"y":1,"w":3,"d":2}',
     ['tag-lab-01']],
  ];
  for (const [id, name, bounds, wps] of ZONES) {
    await admin.conn.reducers.upsertZone({
      id, name, boundsJson: bounds, waypoints: wps,
    });
  }
  const devices: Array<[string, string, string]> = [
    ['puck-a-01', 'puck_contact', 'rack-01'],
    ['puck-wifi-01', 'puck_wifi', 'rack-01'],
    ['puck-b-01', 'puck_contact', 'cabinet-01'],
    ['puck-c-01', 'puck_ble', 'lab-b'],
    ['rover-01', 'rover', 'lobby'],
    ['kismet-01', 'kismet', 'lab-floor'],
    ['sdr-01', 'sdr', 'lab-floor'],
    ['vpi-compute-01', 'other', 'rack-01'],
    ['vpi-network-01', 'other', 'lab-b'],
    ['vpi-sensor-01', 'other', 'rack-01'],
    ['vpi-mgmt-01', 'other', 'bench-row'],
  ];
  for (const [did, dtype, zone] of devices) {
    await admin.conn.reducers.upsertDevice({ id: did, type: dtype, zoneId: zone, firmware: '0.1.0-seed' });
  }
  await admin.conn.reducers.upsertAsset({
    id: 'srv-01',
    zoneId: 'rack-01',
    type: 'server',
    owner: 'lab',
    authorizedNetworkIds: ['corp-lan'],
  });
  console.log('registry: zones/devices/assets seeded');

  // 4) device principals — direct-ingest path (MQTT path uses gateway instead)
  for (const [did] of devices) {
    await admin.conn.reducers.enrollDevicePrincipal({ deviceId: did, identity: id(`device-${did}`) });
  }
  console.log('device principals: enrolled');

  // 5) persist tokens for env injection
  mkdirSync(SECRETS_DIR, { recursive: true });
  allTokens[URI] = saved;
  writeFileSync(TOKENS_FILE, JSON.stringify(allTokens, null, 2));
  console.log(`tokens written -> ${TOKENS_FILE} (gitignored)`);

  // env snippets for gateway.env
  console.log('\n--- gateway.env snippet ---');
  console.log(`SPACETIMEDB_TOKEN=${saved['gateway']}`);
  console.log(`EXECUTOR_SPACETIMEDB_TOKEN=${saved['executor']}`);
  console.log('--------------------------------\n');

  await sleep(300);
  process.exit(0);
}

main().catch((e) => {
  console.error('SEED FAILED', e);
  process.exit(1);
});
