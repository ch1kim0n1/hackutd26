import { describe, expect, it, vi } from 'vitest'
import { LiveSync } from '../src/command/live/sync'
import { fixtureSnapshot } from '../src/command/live/fixture'
import { mapSnapshot } from '../src/command/live/map'
import { emptyRows, type ApiSnapshot, type LiveRows } from '../src/command/live/types'

const apiOk: ApiSnapshot = { reachable: true, detail: 'ok', investigations: [], incidentCount: 0 }
const apiDown: ApiSnapshot = { reachable: false, detail: 'down', investigations: [], incidentCount: null }

describe('LiveSync', () => {
  it('fixture mode emits a REPLAY snapshot immediately', async () => {
    const snapshots: unknown[] = []
    const phases: string[] = []
    const sync = new LiveSync({ fixture: true }, {
      onPhase: (p) => phases.push(p),
      onSnapshot: (s) => snapshots.push(s),
    })
    await sync.start()
    await new Promise(r => setTimeout(r, 250))
    expect(phases).toContain('online')
    expect(snapshots.length).toBeGreaterThan(0)
    expect((snapshots[0] as { provenance: string }).provenance).toBe('REPLAY')
    sync.stop()
  })

  it('real mode merges row + api feeds and reports degraded when API is down', async () => {
    const rows: LiveRows = emptyRows()
    let rowHandler: { onRows(r: LiveRows): void; onStatus(s: string, d: string): void } | null = null
    const snapshots: { provenance: string; api: ApiSnapshot }[] = []
    const phases: string[] = []
    const sync = new LiveSync({
      pollMs: 10,
      rows: { start: async (h) => { rowHandler = h as never; h.onStatus('online', 'connected') }, stop: vi.fn() },
      api: { snapshot: async () => apiDown },
    }, {
      onPhase: (p) => phases.push(p),
      onSnapshot: (s) => snapshots.push(s as never),
    })
    await sync.start()
    rowHandler!.onRows(rows)
    await new Promise(r => setTimeout(r, 300))
    expect(phases).toContain('degraded')
    expect(snapshots.at(-1)!.provenance).toBe('LIVE')
    expect(snapshots.at(-1)!.api.reachable).toBe(false)
    sync.stop()
  })

  it('resync after reconnect emits the same entity ids — no duplicates', async () => {
    const snap = fixtureSnapshot()
    const emitted: string[][] = []
    let rowHandler: { onRows(r: LiveRows): void; onStatus(s: string, d: string): void } | null = null
    const sync = new LiveSync({
      pollMs: 10000,
      rows: { start: async (h) => { rowHandler = h as never }, stop: vi.fn() },
      api: { snapshot: async () => apiOk },
    }, {
      onPhase: () => {},
      onSnapshot: (s) => {
        const { entities } = mapSnapshot(s, 0)
        emitted.push([...entities.observations, ...entities.incidents, ...entities.events].map(e => e.id))
      },
    })
    await sync.start()
    // Simulate two reconnect/resync cycles emitting identical rows.
    rowHandler!.onRows(snap.rows)
    await new Promise(r => setTimeout(r, 300))
    rowHandler!.onRows(snap.rows) // simulated reconnect/resync
    await new Promise(r => setTimeout(r, 300))
    expect(emitted.length).toBeGreaterThanOrEqual(2)
    for (const ids of emitted) expect(new Set(ids).size).toBe(ids.length)
    expect(emitted[0]).toEqual(emitted[1])
    sync.stop()
  })
})
