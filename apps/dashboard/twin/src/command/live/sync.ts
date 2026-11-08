import type { ApiSnapshot, LiveRows, LiveSnapshot } from './types'
import { emptyRows } from './types'
import { mapSnapshot } from './map'

export type LivePhase = 'off' | 'connecting' | 'online' | 'degraded' | 'error'

export interface LiveSyncHandlers {
  onPhase(phase: LivePhase, detail: string): void
  onSnapshot(snapshot: LiveSnapshot): void
}

export interface LiveSyncDeps {
  rows?: { start(h: { onRows(r: LiveRows): void; onStatus(s: 'connecting' | 'online' | 'error', d: string): void }): Promise<void> | void; stop(): void }
  api?: { snapshot(): Promise<ApiSnapshot>; start?(pollMs: number, cb: (s: ApiSnapshot) => void): void; stop?(): void }
  fixture?: boolean
  pollMs?: number
}

/** Orchestrates the two live feeds (SpacetimeDB rows + API snapshot),
 * merges them into LiveSnapshots, and emits on every update. Owns
 * reconnect bookkeeping: the SDK auto-reconnects; the API poll simply
 * retries on its cadence — a missed poll degrades status, never drops
 * entity state (next successful snapshot rebuilds it wholesale). */
export class LiveSync {
  private rows: LiveRows = emptyRows()
  private api: ApiSnapshot = { reachable: false, detail: 'awaiting first poll', investigations: [], incidentCount: null }
  private apiTimer: ReturnType<typeof setInterval> | null = null
  private phase: LivePhase = 'off'
  private detail = ''
  private lastEmit = 0
  private emitTimer: ReturnType<typeof setTimeout> | null = null

  constructor(private deps: LiveSyncDeps, private handlers: LiveSyncHandlers) {}

  get provenance(): 'LIVE' | 'REPLAY' { return this.deps.fixture ? 'REPLAY' : 'LIVE' }

  async start(): Promise<void> {
    if (this.deps.fixture) {
      const { fixtureSnapshot } = await import('./fixture')
      const snap = fixtureSnapshot()
      this.rows = snap.rows
      this.api = snap.api
      this.phase = 'online'
      this.detail = 'REPLAY fixture transport'
      this.handlers.onPhase('online', this.detail)
      this.scheduleEmit()
      return
    }
    this.phase = 'connecting'
    this.detail = 'connecting to backends'
    this.handlers.onPhase('connecting', this.detail)
    const rowsDep = this.deps.rows
    if (rowsDep) {
      await rowsDep.start({
        onRows: (r) => { this.rows = r; this.recomputePhase(); this.scheduleEmit() },
        onStatus: (s, d) => {
          if (s === 'error') { this.phase = 'degraded'; this.detail = d }
          else if (s === 'online') { this.phase = this.api.reachable ? 'online' : 'degraded'; this.detail = d }
          else { if (this.phase !== 'error') this.phase = 'connecting'; this.detail = d }
          this.handlers.onPhase(this.phase, this.detail)
        },
      })
    }
    const apiDep = this.deps.api
    if (apiDep) {
      const poll = async () => {
        this.api = await apiDep.snapshot()
        this.recomputePhase()
        this.scheduleEmit()
      }
      await poll()
      this.apiTimer = setInterval(() => void poll(), this.deps.pollMs ?? 5000)
    }
  }

  private recomputePhase(): void {
    if (this.phase === 'error') return
    this.phase = this.api.reachable ? 'online' : 'degraded'
    this.detail = this.api.reachable ? 'backends streaming' : `SpacetimeDB streaming · ${this.api.detail}`
    this.handlers.onPhase(this.phase, this.detail)
  }

  private scheduleEmit(): void {
    if (this.emitTimer) return
    this.emitTimer = setTimeout(() => {
      this.emitTimer = null
      const backendNowMicros = this.computeBackendNow()
      this.handlers.onSnapshot({
        provenance: this.provenance, rows: this.rows, api: this.api, backendNowMicros,
      })
      this.lastEmit = Date.now()
    }, 100)
  }

  private computeBackendNow(): number {
    let max = 0
    const scan = (v: unknown) => { const t = Number(v); if (Number.isFinite(t) && t > max && t < 1e18) max = t }
    for (const o of this.rows.observations) scan((o as { receivedAt?: unknown }).receivedAt ?? (o as { observedAt?: unknown }).observedAt)
    for (const i of this.rows.incidents) { scan((i as { updatedAt?: unknown }).updatedAt); scan((i as { createdAt?: unknown }).createdAt) }
    for (const a of this.rows.auditEvents) scan((a as { at?: unknown }).at)
    for (const a of this.rows.alerts) scan((a as { createdAt?: unknown }).createdAt)
    return max || Date.now() * 1000
  }

  stop(): void {
    if (this.apiTimer) clearInterval(this.apiTimer)
    if (this.emitTimer) clearTimeout(this.emitTimer)
    this.apiTimer = this.emitTimer = null
    try { this.deps.rows?.stop() } catch { /* ignore */ }
    try { this.deps.api?.stop?.() } catch { /* ignore */ }
    this.phase = 'off'
    this.handlers.onPhase('off', 'live sync stopped')
  }
}
