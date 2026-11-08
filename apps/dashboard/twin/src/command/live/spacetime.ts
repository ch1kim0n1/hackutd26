import { DbConnection } from '../../spacetimedb'
import { emptyRows, type LiveRows } from './types'

/** Views the dashboard consumes. All are role-scoped server-side;
 * anonymous principals receive empty feeds (docs/13 §2). */
const VIEWS = [
  'zoneFeed', 'deviceFeed', 'assetFeed', 'observationFeed', 'incidentFeed',
  'evidenceFeed', 'missionFeed', 'approvalFeed', 'actionFeed', 'scopeFeed',
  'opsAlertFeed', 'auditFeed', 'healthFeed', 'rfFeed',
] as const

type TableObserver = {
  onInsert(cb: () => void): void
  onDelete(cb: () => void): void
  onUpdate?(cb: () => void): void
  removeOnInsert(cb: () => void): void
  removeOnDelete(cb: () => void): void
  removeOnUpdate?(cb: () => void): void
}

/** Listen for changes after the initial subscription, and detach on stop. */
export function observeTables(tables: Record<string, TableObserver>, changed: () => void): () => void {
  const observed = VIEWS.map(name => tables[name]).filter(Boolean)
  for (const table of observed) {
    table.onInsert(changed); table.onDelete(changed); table.onUpdate?.(changed)
  }
  return () => {
    for (const table of observed) {
      table.removeOnInsert(changed); table.removeOnDelete(changed); table.removeOnUpdate?.(changed)
    }
  }
}

export interface SpaceTimeHandlers {
  onRows(rows: LiveRows): void
  onStatus(status: 'connecting' | 'online' | 'error', detail: string): void
}

/** SpacetimeDB transport: authenticated DbConnection + one subscription
 * covering the ops views. Rebuilds the full row set on every applied
 * update and emits it — snapshot semantics make reconnect/resync
 * duplication-proof by construction (same ids → same entities). */
export class SpaceTimeTransport {
  private conn: DbConnection | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private stopped = false
  private unobserve: (() => void) | null = null

  constructor(
    private uri: string,
    private token: string,
    private database: string,
  ) {}

  async start(handlers: SpaceTimeHandlers): Promise<void> {
    this.stopped = false
    handlers.onStatus('connecting', `SpacetimeDB ${this.uri} · db ${this.database}`)
    const conn = DbConnection.builder()
      .withUri(this.uri)
      .withDatabaseName(this.database)
      .withToken(this.token)
      .onConnect(() => {
        handlers.onStatus('online', 'SpacetimeDB connected')
        this.emit(conn, handlers)
      })
      .onConnectError((_ctx, err) => handlers.onStatus('error', `connect error: ${String(err)}`))
      .onDisconnect(() => handlers.onStatus('connecting', 'SpacetimeDB disconnected — reconnecting'))
      .build()
    this.conn = conn
    this.unobserve = observeTables(conn.db as unknown as Record<string, TableObserver>, () => this.emit(conn, handlers))
    conn.subscriptionBuilder()
      .onApplied(() => this.emit(conn, handlers))
      .onError((ctx) => handlers.onStatus('error', `subscription error: ${JSON.stringify(ctx)}`))
      .subscribe((tables) => VIEWS.map((v) => (tables as Record<string, { build(): unknown }>)[v].build() as never))
  }

  private emit(conn: DbConnection, handlers: SpaceTimeHandlers): void {
    if (this.stopped) return
    if (this.timer) clearTimeout(this.timer)
    // Debounce: subscription events arrive per-row; rebuild once per burst.
    this.timer = setTimeout(() => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const db = conn.db as any
        const rows = emptyRows()
        const pick = <K extends keyof LiveRows>(view: string, key: K) => {
          const t = db[view]
          if (t?.iter) rows[key] = [...t.iter()] as LiveRows[K]
        }
        pick('zoneFeed', 'zones'); pick('deviceFeed', 'devices'); pick('assetFeed', 'assets')
        pick('observationFeed', 'observations'); pick('incidentFeed', 'incidents')
        pick('evidenceFeed', 'evidence'); pick('missionFeed', 'missions')
        pick('approvalFeed', 'approvals'); pick('actionFeed', 'actions')
        pick('scopeFeed', 'scopeEntries'); pick('opsAlertFeed', 'alerts')
        pick('auditFeed', 'auditEvents'); pick('healthFeed', 'health'); pick('rfFeed', 'rfFrames')
        handlers.onRows(rows)
      } catch (error) {
        handlers.onStatus('error', `row decode failed: ${error instanceof Error ? error.message : String(error)}`)
      }
    }, 120)
  }

  stop(): void {
    this.stopped = true
    if (this.timer) clearTimeout(this.timer)
    this.unobserve?.(); this.unobserve = null
    try { this.conn?.disconnect() } catch { /* ignore */ }
    this.conn = null
  }
}
