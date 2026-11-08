// Initialize an explicitly named NEW physical-demo database without wiping
// or altering any other database. Tokens are read locally and never printed.
import { readFileSync } from 'node:fs'
import { DbConnection } from '../bindings/index'
import type { Identity } from 'spacetimedb'

const uri = process.env.SPACETIMEDB_URI ?? 'ws://127.0.0.1:3000'
const db = process.env.SPACETIMEDB_DATABASE ?? ''
if (!/^blindspot-physical-[a-z0-9-]+$/.test(db) || process.env.BLINDSPOT_ALLOW_EMPTY_BOOTSTRAP !== '1') {
  throw new Error('Explicit new blindspot-physical database and empty-bootstrap flag required')
}
const tokenFile = process.env.BLINDSPOT_IDENTITIES_FILE ?? '../../deploy/secrets/identities.json'
const tokens = JSON.parse(readFileSync(tokenFile, 'utf8'))[uri] as Record<string, string>
const roles = ['admin', 'commander', 'responder', 'observer', 'agent', 'gateway', 'executor'] as const
if (!tokens || roles.some(role => !tokens[role])) throw new Error('Required local role identities are missing')

async function connect(token: string): Promise<{ conn: DbConnection; id: Identity }> {
  return new Promise((resolve, reject) => DbConnection.builder().withUri(uri).withDatabaseName(db).withToken(token)
    .onConnect((conn, id) => resolve({ conn, id })).onConnectError((_ctx, error) => reject(error)).build())
}
const sessions = new Map<string, { conn: DbConnection; id: Identity }>()
try {
  for (const role of roles) sessions.set(role, await connect(tokens[role]))
  const admin = sessions.get('admin')!.conn
  // Must succeed on an empty directory; do not proceed on an initialized DB.
  await admin.reducers.bootstrapAdmin({ note: 'physical-demo initialization' })
  for (const role of roles.slice(1)) {
    await admin.reducers.upsertUserRole({ userId: sessions.get(role)!.id, role, incidentScope: [], note: 'physical-demo role' })
  }
  for (const id of ['rack-01', 'rack-02']) {
    // Locations are not surveyed yet: no fabricated coordinates or waypoints.
    await admin.reducers.upsertZone({ id, name: id, boundsJson: '{}', waypoints: [] })
  }
  for (const [id, zoneId] of [['pi-01', 'rack-01'], ['pi-02', 'rack-02']]) {
    await admin.reducers.upsertDevice({ id, type: 'other', zoneId, firmware: 'physical-monitor' })
  }
  console.log('Initialized physical-demo roles, two zones, and pi-01/pi-02')
} finally {
  for (const { conn } of sessions.values()) conn.disconnect()
}
