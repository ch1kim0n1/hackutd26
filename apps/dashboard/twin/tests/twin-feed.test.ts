import { describe, expect, it } from 'vitest'
import {
  OCCUPANCY_GRID_CONTRACT, POSE_REPORT_CONTRACT, TwinContractError,
  contractTimestampMicros, frameToFacility, normalizeOccupancyCells,
  parseOccupancyGrid, parsePoseReport, registerFrame,
} from '../src/command/twin/occupancyContract'
import {
  OccupancyInstanceSet, contractToTwinMap, inferredRectHeight,
  mergeCellRects, planTwinInstances,
} from '../src/command/twin/occupancyMesh'
import { simAnchors, simOccupancyContract, simTwinUpdate } from '../src/command/twin/simFeed'
import { mapTwinFeed, SimTwinTransport, HttpTwinTransport } from '../src/command/live/twin'
import { mapRover, mapSnapshot } from '../src/command/live/map'
import { emptyRows, type ApiSnapshot, type LiveRows, type LiveSnapshot } from '../src/command/live/types'
import { createInitialState } from '../src/command/fixtures'
import { withTwinFeed } from '../src/command/engine'
import type { MapContext } from '../src/command/live/map'

const NOW_MICROS = 1_760_000_000_000_000
const ctx: MapContext = { elapsed: 100, backendNowMicros: NOW_MICROS, provenance: 'REPLAY' }

function gridPayload(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    contract: OCCUPANCY_GRID_CONTRACT, schema_version: 1,
    frame_id: 'surveyed_floorplan', resolution_m: 0.5,
    width: 4, height: 3, origin: { x: 1, y: 2 },
    revision: 7, timestamp: new Date(NOW_MICROS / 1000).toISOString(),
    cells: [
      -1, 0, 100, 0,
      0, 100, 100, -1,
      0, 0, -1, -1,
    ],
    anchors: [{ id: 'pi-1', x: 1.5, y: 2.5, label: 'PI-1' }],
    ...overrides,
  }
}

function posePayload(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    contract: POSE_REPORT_CONTRACT, schema_version: 1,
    device_id: 'rover-01', x: 3, y: 4, theta: 1.25,
    frame_id: 'surveyed_floorplan', unit: 'm',
    timestamp: new Date(NOW_MICROS / 1000).toISOString(),
    ...overrides,
  }
}

function snapshot(partial: Partial<LiveSnapshot> = {}): LiveSnapshot {
  const api: ApiSnapshot = { reachable: true, detail: 'ok', investigations: [], incidentCount: 0 }
  return { provenance: 'REPLAY', rows: emptyRows(), api, backendNowMicros: NOW_MICROS, ...partial }
}

describe('occupancy grid contract', () => {
  it('parses a valid -1/0/100 grid with counts and anchors', () => {
    const g = parseOccupancyGrid(gridPayload())
    expect(g.frameId).toBe('surveyed_floorplan')
    expect(g.revision).toBe(7)
    expect(g.resolutionM).toBe(0.5)
    expect(g.origin).toEqual({ x: 1, y: 2 })
    expect(g.timestampMicros).toBe(NOW_MICROS)
    expect(g.counts).toEqual({ unknown: 4, free: 5, occupied: 3 })
    expect(g.cells[2]).toBe(100)
    expect(g.cells[0]).toBe(-1)
    expect(g.anchors).toEqual([{ id: 'pi-1', x: 1.5, y: 2.5, label: 'PI-1' }])
  })

  it('normalizes legacy 0..1 probability cells to canonical -1/0/100', () => {
    const cells = normalizeOccupancyCells([0, 0.4, 0.5, 1, -1, 0.49])
    expect([...cells]).toEqual([0, 0, 100, 100, -1, 0])
    // Canonical scale is untouched.
    expect([...normalizeOccupancyCells([0, 50, 100, -1])]).toEqual([0, 100, 100, -1])
  })

  it('accepts typed-array cells', () => {
    const g = parseOccupancyGrid(gridPayload({ cells: Int16Array.from([0, 100, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0]) }))
    expect(g.counts).toEqual({ unknown: 1, free: 10, occupied: 1 })
  })

  it('rejects malformed payloads instead of fabricating geometry', () => {
    expect(() => parseOccupancyGrid(null)).toThrow(TwinContractError)
    expect(() => parseOccupancyGrid(gridPayload({ contract: 'other' }))).toThrow(TwinContractError)
    expect(() => parseOccupancyGrid(gridPayload({ schema_version: 2 }))).toThrow(TwinContractError)
    expect(() => parseOccupancyGrid(gridPayload({ width: 0 }))).toThrow(TwinContractError)
    expect(() => parseOccupancyGrid(gridPayload({ width: 4, height: 3, cells: [0, 1] }))).toThrow(TwinContractError)
    expect(() => parseOccupancyGrid(gridPayload({ resolution_m: -1 }))).toThrow(TwinContractError)
    expect(() => parseOccupancyGrid(gridPayload({ revision: -1 }))).toThrow(TwinContractError)
    expect(() => parseOccupancyGrid(gridPayload({ cells: [0, 101, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] }))).toThrow(TwinContractError)
    expect(() => parseOccupancyGrid(gridPayload({ timestamp: 'not-a-date' }))).toThrow(TwinContractError)
  })

  it('enforces hard size limits', () => {
    const big = new Array(513 * 513).fill(0)
    expect(() => parseOccupancyGrid(gridPayload({ width: 513, height: 513, cells: big }))).toThrow(TwinContractError)
  })

  it('parses pose reports including mm units and heading aliases', () => {
    const p = parsePoseReport(posePayload())
    expect(p.x).toBe(3); expect(p.y).toBe(4); expect(p.theta).toBe(1.25)
    expect(p.timestampMicros).toBe(NOW_MICROS)
    const mm = parsePoseReport(posePayload({ unit: 'mm', x: 1500, y: -2000, theta: undefined, heading_rad: 0.5 }))
    expect(mm.x).toBe(1.5); expect(mm.y).toBe(-2); expect(mm.theta).toBe(0.5)
    expect(() => parsePoseReport(posePayload({ theta: undefined, heading_rad: undefined }))).toThrow(TwinContractError)
    expect(() => parsePoseReport(posePayload({ device_id: '' }))).toThrow(TwinContractError)
  })

  it('converts epoch seconds/ms/us timestamps heuristically', () => {
    expect(contractTimestampMicros(1_760_000_000)).toBe(1_760_000_000_000_000)
    expect(contractTimestampMicros(1_760_000_000_000)).toBe(1_760_000_000_000_000)
    expect(contractTimestampMicros(1_760_000_000_000_000)).toBe(1_760_000_000_000_000)
  })
})

describe('frame registration', () => {
  it('identity-registers surveyed frames and offsets autonomy_map', () => {
    expect(frameToFacility({ x: 3, y: 4 }, 'surveyed_floorplan')).toEqual({ x: 3, y: 4 })
    expect(frameToFacility({ x: 3, y: 4 }, 'facility')).toEqual({ x: 3, y: 4 })
    expect(frameToFacility({ x: 3, y: 4 }, 'autonomy_map')).toEqual({ x: 15, y: 13 })
  })
  it('never silently places unregistered frames', () => {
    expect(registerFrame('mystery_frame').kind).toBe('unregistered')
    expect(frameToFacility({ x: 3, y: 4 }, 'mystery_frame')).toBeNull()
  })
})

describe('occupancy mesh planning', () => {
  const baseMap = contractToTwinMap(parseOccupancyGrid(gridPayload()), 'REPLAY', 100, NOW_MICROS).map

  it('merges occupied cells into deterministic maximal rects', () => {
    const rects = mergeCellRects(4, 3, (ix, iy) => iy === 1 && ix >= 1 && ix <= 2)
    expect(rects).toEqual([{ x0: 1, y0: 1, x1: 3, y1: 2 }])
    // Same input -> identical output (row-major discovery order).
    expect(mergeCellRects(4, 3, (ix, iy) => iy === 1 && ix >= 1 && ix <= 2)).toEqual(rects)
  })

  it('produces world-space instances with map +y -> world -Z', () => {
    const plan = planTwinInstances(baseMap)
    expect(plan.occupied).toHaveLength(2) // two separate occupied cells
    const single = plan.occupied.find(i => i.key.includes('2,0,3,1'))!
    expect(single.cx).toBeCloseTo(1 + 2.5 * 0.5) // origin.x + cell centre
    expect(single.cz).toBeCloseTo(-(2 + 0.5 * 0.5)) // -(origin.y + cell centre)
    expect(single.sy).toBeGreaterThan(0)
    expect(plan.unknown.length).toBeGreaterThan(0)
    for (const inst of [...plan.occupied, ...plan.unknown]) {
      expect(inst.sy).toBeLessThan(2) // inferred heights stay presentation-scale
    }
  })

  it('infers deterministic heights that never pretend to be measurements', () => {
    const rect = { x0: 1, y0: 1, x1: 3, y1: 2 }
    const h1 = inferredRectHeight(rect, 'surveyed_floorplan')
    expect(h1).toBe(inferredRectHeight(rect, 'surveyed_floorplan'))
    expect(h1).toBeGreaterThanOrEqual(0.35)
    expect(h1).toBeLessThanOrEqual(1.3)
  })

  it('updates instances incrementally — unchanged rects produce no writes', () => {
    const set = new OccupancyInstanceSet('occupied')
    const first = planTwinInstances(baseMap).occupied
    const r1 = set.update(first)
    expect(r1.writes.length).toBe(first.length)
    // Identical plan -> zero writes.
    expect(set.update(first).writes).toHaveLength(0)
    // Drop one rect -> exactly one clearing write.
    const r3 = set.update(first.slice(1))
    expect(r3.writes).toHaveLength(1)
    expect(r3.writes[0].instance).toBeNull()
    // Re-add -> one write back into a recycled slot.
    const r4 = set.update(first)
    expect(r4.writes).toHaveLength(1)
    expect(r4.writes[0].slot).toBe(r3.writes[0].slot)
  })
})

describe('mapTwinFeed', () => {
  it('extracts embedded occupancy + pose contracts from observation dataJson', () => {
    const rows = emptyRows()
    rows.observations = [{
      id: 1n, eventId: 'e1', deviceId: 'rover-01', kind: 'telemetry', seq: 1n,
      observedAt: NOW_MICROS, receivedAt: NOW_MICROS, zoneId: 'ops-floor',
      dataJson: JSON.stringify({ nested: { payloads: [gridPayload(), posePayload()] } }),
      trustTier: { tag: 'GatewayValidated' }, traceId: 't',
    } as never]
    const { twinFeed, poseFixes } = mapTwinFeed(snapshot({ rows }), { ...ctx })
    expect(twinFeed.maps).toHaveLength(1)
    expect(twinFeed.maps[0].frameId).toBe('surveyed_floorplan')
    expect(twinFeed.maps[0].revision).toBe(7)
    expect(twinFeed.maps[0].provenance).toBe('REPLAY')
    expect(twinFeed.maps[0].registered).toBe(true)
    expect(twinFeed.maps[0].stale).toBe(false)
    expect(twinFeed.anchors.map(a => a.id)).toContain('pi-1')
    expect(poseFixes).toHaveLength(1)
    expect(poseFixes[0].x).toBe(3)
    expect(poseFixes[0].frameId).toBe('surveyed_floorplan')
  })

  it('keeps only the newest revision per frame_id', () => {
    const twin = {
      maps: [
        gridPayload({ revision: 3, timestamp: new Date((NOW_MICROS - 10_000_000) / 1000).toISOString() }),
        gridPayload({ revision: 9, timestamp: new Date((NOW_MICROS - 10_000_000) / 1000).toISOString() }),
        gridPayload({ revision: 9, timestamp: new Date((NOW_MICROS - 5_000_000) / 1000).toISOString() }),
      ],
      poses: [], anchors: [], provenance: 'DEMO' as const, detail: 'test',
    }
    const { twinFeed } = mapTwinFeed(snapshot({ twin }), { ...ctx })
    expect(twinFeed.maps).toHaveLength(1)
    expect(twinFeed.maps[0].revision).toBe(9)
    // Equal revision -> newest timestamp wins (5s-old beats 10s-old).
    expect(twinFeed.maps[0].ageSeconds).toBeCloseTo(5, 0)
  })

  it('keeps maps from different frames side by side', () => {
    const twin = {
      maps: [gridPayload(), gridPayload({ frame_id: 'other_frame', revision: 1 })],
      poses: [], anchors: [], provenance: 'DEMO' as const, detail: 'test',
    }
    const { twinFeed } = mapTwinFeed(snapshot({ twin }), { ...ctx })
    expect(twinFeed.maps).toHaveLength(2)
    const unreg = twinFeed.maps.find(m => m.frameId === 'other_frame')!
    expect(unreg.registered).toBe(false)
    // Unregistered maps keep raw origin — never silently transformed.
    expect(unreg.origin).toEqual({ x: 1, y: 2 })
  })

  it('skips malformed contract payloads without fabricating geometry', () => {
    const twin = {
      maps: [gridPayload({ width: 'bad' }), gridPayload({ revision: 4 })],
      poses: [posePayload({ device_id: '' })],
      anchors: [], provenance: 'DEMO' as const, detail: 'test',
    }
    const { twinFeed, poseFixes } = mapTwinFeed(snapshot({ twin }), { ...ctx })
    expect(twinFeed.maps).toHaveLength(1)
    expect(twinFeed.maps[0].revision).toBe(4)
    expect(poseFixes).toHaveLength(0)
  })

  it('applies frame registration to poses and flags unregistered frames', () => {
    const twin = {
      maps: [],
      poses: [
        posePayload({ frame_id: 'autonomy_map', x: 1, y: 1 }),
        posePayload({ device_id: 'rover-01', frame_id: 'alien', x: 9, y: 9 }),
      ],
      anchors: [], provenance: 'LIVE' as const, detail: 'test',
    }
    const { poseFixes } = mapTwinFeed(snapshot({ twin }), { ...ctx })
    const registered = poseFixes.find(p => p.frameId === 'autonomy_map')!
    expect(registered.x).toBe(13); expect(registered.y).toBe(10) // +12/+9 offset
    const alien = poseFixes.find(p => p.frameId === 'alien')!
    expect(alien.x).toBe(9); expect(alien.frameId).toBe('alien')
  })

  it('marks maps stale when their timestamp ages past the threshold', () => {
    const stalePayload = gridPayload({
      timestamp: new Date((NOW_MICROS - 60_000_000) / 1000).toISOString(),
    })
    const { twinFeed } = mapTwinFeed(
      snapshot({ twin: { maps: [stalePayload], poses: [], anchors: [], provenance: 'DEMO', detail: 't' } }),
      { ...ctx },
    )
    expect(twinFeed.maps[0].stale).toBe(true)
    expect(twinFeed.maps[0].ageSeconds).toBeCloseTo(60, 0)
  })

  it('accepts anchors and registered_devices arrays from feed payloads', () => {
    const twin = {
      maps: [], poses: [],
      anchors: [{ id: 'pi-x', x: 2, y: 3, label: 'PI-X', frame_id: 'surveyed_floorplan' }],
      provenance: 'DEMO' as const, detail: 't',
    }
    const { twinFeed } = mapTwinFeed(snapshot({ twin }), { ...ctx })
    expect(twinFeed.anchors).toEqual([{ id: 'pi-x', x: 2, y: 3, label: 'PI-X', frameId: 'surveyed_floorplan' }])
  })
})

describe('rover pose integration', () => {
  const roverRows = (): LiveRows => {
    const rows = emptyRows()
    rows.devices = [{ id: 'rover-01', type: { tag: 'Rover' }, zoneId: 'ops-floor', status: { tag: 'Online' }, lastSeen: NOW_MICROS, lastSeq: 1n, firmware: '' } as never]
    rows.zones = [{ id: 'ops-floor', name: 'Ops', boundsJson: '{"x":0,"y":0,"w":10,"h":10}', waypoints: '[]', updatedAt: NOW_MICROS } as never]
    return rows
  }

  it('merges contract pose fixes into rover state newest-wins', () => {
    const fixes = [{
      deviceId: 'rover-01', x: 5, y: 6, heading: 0.7,
      atMicros: NOW_MICROS - 1_000_000, frameId: 'surveyed_floorplan', provenance: 'DEMO',
    }]
    const rover = mapRover(roverRows(), ctx, [], fixes)
    expect(rover.position).toEqual({ x: 5, y: 6 })
    expect(rover.heading).toBeCloseTo(0.7)
    expect(rover.stale).toBe(false)
    expect(rover.provenance).toBe('DEMO')
    expect(rover.frameId).toBe('surveyed_floorplan')
    expect(rover.poseAt).toBeDefined()
  })

  it('flags stale pose telemetry and zeroes speed', () => {
    const fixes = [{
      deviceId: 'rover-01', x: 5, y: 6, heading: 0,
      atMicros: NOW_MICROS - 30_000_000, frameId: 'surveyed_floorplan',
    }]
    const rover = mapRover(roverRows(), ctx, [], fixes)
    expect(rover.stale).toBe(true)
    expect(rover.speed).toBe(0)
  })

  it('ignores contract fixes from non-rover devices', () => {
    const fixes = [{
      deviceId: 'sensor-99', x: 5, y: 6, heading: 0,
      atMicros: NOW_MICROS, frameId: 'surveyed_floorplan',
    }]
    const rover = mapRover(roverRows(), ctx, [], fixes)
    expect(rover.stale).toBe(true) // fell back to anchor, no pose
    expect(rover.position).not.toEqual({ x: 5, y: 6 })
  })

  it('mapSnapshot populates twinFeed end-to-end', () => {
    const twin = {
      maps: [gridPayload()], poses: [posePayload()], anchors: [],
      provenance: 'DEMO' as const, detail: 'test',
    }
    const { entities } = mapSnapshot(snapshot({ rows: roverRows(), twin }), 100)
    expect(entities.twinFeed.maps).toHaveLength(1)
    expect(entities.rover.position).toEqual({ x: 3, y: 4 })
    expect(entities.rover.provenance).toBe('DEMO')
  })
})

describe('simulated twin feed', () => {
  it('produces contract-valid payloads with registered frames', () => {
    const { maps, poses, anchors } = simTwinUpdate(6, NOW_MICROS)
    expect(maps).toHaveLength(1)
    expect(poses).toHaveLength(1)
    const g = parseOccupancyGrid(maps[0])
    expect(g.frameId).toBe('surveyed_floorplan')
    expect(g.revision).toBe(6)
    const p = parsePoseReport(poses[0])
    expect(p.frameId).toBe('autonomy_map')
    expect(p.provenance).toBe('SIM')
    expect(anchors.length).toBeGreaterThan(0)
    expect(simAnchors().every(a => typeof a.id === 'string')).toBe(true)
  })

  it('SimTwinTransport ticks on a timer and can be stopped', async () => {
    const updates: { provenance: string; maps: unknown[] }[] = []
    const transport = new SimTwinTransport(20, 'REPLAY')
    transport.start(u => updates.push(u), { nowMicros: () => NOW_MICROS })
    await new Promise(r => setTimeout(r, 70))
    transport.stop()
    expect(updates.length).toBeGreaterThanOrEqual(2)
    expect(updates[0].provenance).toBe('REPLAY')
    // Maps emit every `mapEvery` steps — at least one tick must carry one.
    expect(updates.some(u => u.maps.length > 0)).toBe(true)
  })

  it('HttpTwinTransport parses a feed response and survives failures', async () => {
    const calls: string[] = []
    const fetchImpl = (async (url: string) => {
      calls.push(url)
      if (calls.length === 1) throw new Error('offline')
      return {
        ok: true,
        json: async () => ({
          maps: [gridPayload()], poses: [posePayload()],
          anchors: [{ id: 'pi-1', x: 1, y: 1 }],
        }),
      } as Response
    }) as typeof fetch
    const updates: { provenance: string; maps: unknown[]; anchors: unknown[] }[] = []
    const transport = new HttpTwinTransport('http://twin.local/feed', 10, fetchImpl)
    transport.start(u => updates.push(u))
    await new Promise(r => setTimeout(r, 40))
    transport.stop()
    expect(calls.length).toBeGreaterThanOrEqual(2)
    expect(updates.length).toBeGreaterThanOrEqual(1) // failed polls emit nothing
    expect(updates[0].provenance).toBe('LIVE')
    expect(updates[0].maps).toHaveLength(1)
    expect(updates[0].anchors).toHaveLength(1)
  })
})

describe('demo-mode twin feed', () => {
  it('withTwinFeed populates a DEMO-labelled map idempotently per revision', () => {
    const s0 = createInitialState('patrol')
    const s1 = withTwinFeed(s0)
    expect(s1.twinFeed.maps).toHaveLength(1)
    expect(s1.twinFeed.maps[0].provenance).toBe('DEMO')
    expect(s1.twinFeed.maps[0].registered).toBe(true)
    expect(s1.twinFeed.anchors.length).toBeGreaterThan(0)
    // Same elapsed -> same object (no churn).
    expect(withTwinFeed(s1)).toBe(s1)
    // +2s elapsed -> new revision.
    const s2 = withTwinFeed({ ...s1, elapsed: s1.elapsed + 2 })
    expect(s2.twinFeed.maps[0].revision).toBe(s1.twinFeed.maps[0].revision + 1)
  })
})

describe('rendering performance', () => {
  it('plans facility-scale sim maps well under frame budget', () => {
    const { map } = contractToTwinMap(
      parseOccupancyGrid(simOccupancyContract(12, NOW_MICROS)), 'DEMO', 100, NOW_MICROS,
    )
    const start = performance.now()
    const plan = planTwinInstances(map)
    const elapsed = performance.now() - start
    expect(plan.occupied.length + plan.unknown.length).toBeGreaterThan(0)
    expect(elapsed).toBeLessThan(100) // 96x72 grid; budget is generous for CI
  })

  it('incremental revision updates touch only changed instances', () => {
    const mkMap = (step: number) => contractToTwinMap(
      parseOccupancyGrid(simOccupancyContract(step, NOW_MICROS)), 'DEMO', 100, NOW_MICROS,
    ).map
    const set = new OccupancyInstanceSet('occupied')
    const a = planTwinInstances(mkMap(3)).occupied
    set.update(a)
    // Single-cell change: one free cell -> occupied produces a tiny
    // write set, not a full re-plan.
    const mapA = mkMap(3)
    const cells = mapA.cells.slice()
    const idx = cells.indexOf(0)
    cells[idx] = 100
    const mapB = { ...mapA, revision: 4, cells }
    const b = planTwinInstances(mapB).occupied
    const result = set.update(b)
    expect(result.writes.length).toBeGreaterThan(0)
    expect(result.writes.length).toBeLessThanOrEqual(4)
    expect(result.writes.length).toBeLessThan(b.length)
  })

  it('handles a worst-case dense 512x512 grid without pathological cost', () => {
    const cells = new Array(512 * 512)
    for (let i = 0; i < cells.length; i += 1) cells[i] = (i * 7) % 11 === 0 ? 100 : i % 3 === 0 ? -1 : 0
    const g = parseOccupancyGrid(gridPayload({ width: 512, height: 512, resolution_m: 0.5, cells }))
    const { map } = contractToTwinMap(g, 'DEMO', 100, NOW_MICROS)
    const start = performance.now()
    const plan = planTwinInstances(map)
    expect(performance.now() - start).toBeLessThan(500)
    // Pathological scatter still plans in bounded time; the renderer's
    // instance cap (8192/layer) bounds what actually reaches the GPU.
    expect(plan.occupied.length + plan.unknown.length).toBeLessThan(150_000)
  })
})
