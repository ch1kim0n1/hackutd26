import {
  OCCUPANCY_GRID_CONTRACT, POSE_REPORT_CONTRACT, TwinContractError,
  frameToFacility, parseOccupancyGrid, parsePoseReport,
  type ParsedOccupancyGrid, type ParsedPoseReport,
} from '../twin/occupancyContract'
import { contractToTwinMap } from '../twin/occupancyMesh'
import { simTwinUpdate } from '../twin/simFeed'
import { toMicros } from './time'
import type { LiveSnapshot, TwinFeedUpdate } from './types'
import type { TwinAnchor, TwinFeedState, TwinProvenance } from '../model'

/**
 * Twin spatial feed adapters (docs/13 §9). Two ingest paths, one
 * normalized output:
 *
 *  1. Contract payloads embedded in observation `dataJson` — works with
 *     the frozen gateway/OBSERVATION_KINDS pipeline today for payloads
 *     under the 8 KiB data cap (small maps, pose reports, anchors).
 *  2. A dedicated `TwinFeedTransport` (simulated now; an HTTP endpoint
 *     is the documented backend integration request) for full-size
 *     maps that cannot ride telemetry envelopes.
 *
 * Everything here is read-only and provenance-preserving: simulated
 * feeds are labelled DEMO/REPLAY, never LIVE.
 */

export interface TwinCtx {
  elapsed: number
  backendNowMicros: number
  provenance: 'LIVE' | 'REPLAY'
}

/** A pose fix in facility coordinates, ready for mapRover. */
export interface TwinPoseFix {
  deviceId: string
  x: number
  y: number
  heading: number
  atMicros: number
  frameId: string
  provenance?: string
}

interface Candidate {
  payload: unknown
  provenance: TwinProvenance
  /** Arrival time fallback (epoch micros) when the payload lacks a
   * usable timestamp. */
  atMicros: number
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

const MAP_KEYS = new Set(['occupancy_grid', 'occupancyGrid', 'grid', 'map'])
const POSE_KEYS = new Set(['pose_report', 'poseReport', 'pose_contract'])
const TWIN_PROVENANCES = new Set(['LIVE', 'REPLAY', 'DEMO'])

/** Per-payload provenance override: a feed may mix LIVE pose fixes with
 * DEMO simulated maps on one response — the payload's own label wins over
 * the transport default. Unknown values fall back (never upgraded). */
function provOf(v: unknown, fallback: TwinProvenance): TwinProvenance {
  return typeof v === 'string' && TWIN_PROVENANCES.has(v) ? v as TwinProvenance : fallback
}

/** Depth-bounded walk collecting contract payloads. Discriminator
 * (`contract`) matches win; conventional carrier keys get schema
 * defaults injected so producers can omit boilerplate. */
function collectPayloads(
  root: unknown, provenance: TwinProvenance, atMicros: number,
  maps: Candidate[], poses: Candidate[], depth = 0,
): void {
  if (depth > 5 || root === null || typeof root !== 'object') return
  if (Array.isArray(root)) {
    for (const v of root) collectPayloads(v, provenance, atMicros, maps, poses, depth + 1)
    return
  }
  const o = root as Record<string, unknown>
  if (o.contract === OCCUPANCY_GRID_CONTRACT) { maps.push({ payload: o, provenance: provOf(o.provenance, provenance), atMicros }); return }
  if (o.contract === POSE_REPORT_CONTRACT) { poses.push({ payload: o, provenance: provOf(o.provenance, provenance), atMicros }); return }
  for (const [key, value] of Object.entries(o)) {
    if (isRecord(value) && MAP_KEYS.has(key)) {
      maps.push({
        payload: { schema_version: 1, ...value, contract: value.contract ?? OCCUPANCY_GRID_CONTRACT },
        provenance: provOf(value.provenance, provenance), atMicros,
      })
      continue
    }
    if (isRecord(value) && POSE_KEYS.has(key)) {
      poses.push({
        payload: { schema_version: 1, ...value, contract: value.contract ?? POSE_REPORT_CONTRACT },
        provenance: provOf(value.provenance, provenance), atMicros,
      })
      continue
    }
    if (value !== null && typeof value === 'object') {
      collectPayloads(value, provenance, atMicros, maps, poses, depth + 1)
    }
  }
}

function microsToIso(micros: number): string | undefined {
  if (!micros || micros <= 0) return undefined
  const ms = micros / 1000
  if (ms > 8.64e15 || ms < 0) return undefined
  return new Date(ms).toISOString()
}

/** Scan every observation's dataJson for embedded twin contracts. */
function collectFromRows(rows: LiveSnapshot['rows'], provenance: TwinProvenance, maps: Candidate[], poses: Candidate[]): void {
  for (const o of rows.observations) {
    if (!o.dataJson) continue
    let parsed: unknown
    try { parsed = JSON.parse(o.dataJson) } catch { continue }
    collectPayloads(parsed, provenance, toMicros(o.observedAt || o.receivedAt), maps, poses)
  }
}

function parseAnchorPayload(v: unknown): TwinAnchor[] {
  if (!Array.isArray(v)) return []
  const out: TwinAnchor[] = []
  for (const a of v.slice(0, 512)) {
    if (!isRecord(a) || typeof a.id !== 'string' || !Number.isFinite(a.x) || !Number.isFinite(a.y)) continue
    const frameId = typeof a.frame_id === 'string' ? a.frame_id : typeof a.frameId === 'string' ? a.frameId : 'surveyed_floorplan'
    const p = frameToFacility({ x: a.x as number, y: a.y as number }, frameId)
    if (!p) continue
    const anchor: TwinAnchor = { id: a.id, x: p.x, y: p.y, frameId }
    if (typeof a.label === 'string') anchor.label = a.label.slice(0, 64)
    out.push(anchor)
  }
  return out
}

function betterMap(a: ParsedOccupancyGrid, b: ParsedOccupancyGrid): ParsedOccupancyGrid {
  // Latest revision wins; equal revision -> newest timestamp; equal -> keep first.
  if (a.revision !== b.revision) return a.revision > b.revision ? a : b
  return a.timestampMicros >= b.timestampMicros ? a : b
}

/** Merge observation-embedded contracts + dedicated feed payloads into
 * the normalized TwinFeedState, plus facility-frame pose fixes for the
 * rover mapper. Deterministic: same snapshot -> same output. */
export function mapTwinFeed(
  snapshot: LiveSnapshot, ctx: TwinCtx,
): { twinFeed: TwinFeedState; poseFixes: TwinPoseFix[] } {
  const mapCandidates: Candidate[] = []
  const poseCandidates: Candidate[] = []
  collectFromRows(snapshot.rows, snapshot.provenance, mapCandidates, poseCandidates)

  const feedAnchors: TwinAnchor[] = []
  const twin = snapshot.twin
  if (twin) {
    const prov = twin.provenance
    const at = snapshot.backendNowMicros
    for (const m of twin.maps) collectPayloads(m, prov, at, mapCandidates, poseCandidates)
    for (const p of twin.poses) collectPayloads(p, prov, at, mapCandidates, poseCandidates)
    feedAnchors.push(...parseAnchorPayload(twin.anchors))
  }

  // Backfill `timestamp` from the observation arrival time when a
  // producer omits it (telemetry envelopes carry observed_at outside
  // the contract payload).
  for (const list of [mapCandidates, poseCandidates]) {
    for (const c of list) {
      if (isRecord(c.payload) && c.payload.timestamp === undefined) {
        const iso = microsToIso(c.atMicros)
        if (iso) c.payload = { ...c.payload, timestamp: iso }
      }
    }
  }

  // Parse + dedupe maps per frame_id (latest revision wins).
  const byFrame = new Map<string, { grid: ParsedOccupancyGrid; provenance: TwinProvenance }>()
  for (const c of mapCandidates) {
    try {
      const grid = parseOccupancyGrid(c.payload)
      const prev = byFrame.get(grid.frameId)
      if (!prev || betterMap(grid, prev.grid) === grid) byFrame.set(grid.frameId, { grid, provenance: c.provenance })
    } catch (error) {
      if (!(error instanceof TwinContractError)) throw error
      // Malformed maps are skipped, never fabricated into geometry.
    }
  }

  const maps: TwinFeedState['maps'] = []
  const anchors: TwinAnchor[] = [...feedAnchors]
  const seenAnchor = new Set(anchors.map(a => a.id))
  for (const frameId of [...byFrame.keys()].sort()) {
    const { grid, provenance } = byFrame.get(frameId)!
    const { map, anchors: mapAnchors } = contractToTwinMap(grid, provenance, ctx.elapsed, ctx.backendNowMicros)
    maps.push(map)
    for (const a of mapAnchors) {
      if (seenAnchor.has(a.id)) continue
      seenAnchor.add(a.id)
      anchors.push(a)
    }
  }

  // Parse pose reports -> facility-frame fixes.
  const poseFixes: TwinPoseFix[] = []
  for (const c of poseCandidates) {
    let pose: ParsedPoseReport
    try { pose = parsePoseReport(c.payload) } catch (error) {
      if (!(error instanceof TwinContractError)) throw error
      continue
    }
    const facility = frameToFacility({ x: pose.x, y: pose.y }, pose.frameId)
    poseFixes.push({
      deviceId: pose.deviceId,
      // Unregistered frames keep raw coords (same convention as the
      // mission_status path) — frameId is surfaced so the UI can label it.
      x: facility?.x ?? pose.x,
      y: facility?.y ?? pose.y,
      heading: pose.theta,
      atMicros: pose.timestampMicros || c.atMicros,
      frameId: pose.frameId,
      provenance: pose.provenance ?? c.provenance,
    })
  }
  poseFixes.sort((a, b) => a.atMicros - b.atMicros)
  return { twinFeed: { maps, anchors }, poseFixes }
}

// ---------------------------------------------------------------------------
// Transports
// ---------------------------------------------------------------------------

export interface TwinFeedTransport {
  start(onUpdate: (u: TwinFeedUpdate) => void, clock: { nowMicros(): number }): void
  stop(): void
}

/** Simulated twin feed for tests/demos before hardware exists. Emits
 * contract payloads on a timer; provenance is caller-labelled
 * (REPLAY under fixture transport, DEMO under ?twin=sim). */
export class SimTwinTransport implements TwinFeedTransport {
  private timer: ReturnType<typeof setInterval> | null = null
  private step = 0

  constructor(
    private intervalMs = 600,
    private provenance: TwinFeedUpdate['provenance'] = 'DEMO',
    private mapEvery = 3,
  ) {}

  start(onUpdate: (u: TwinFeedUpdate) => void, clock: { nowMicros(): number }): void {
    this.stop()
    const tick = () => {
      this.step += 1
      const payload = simTwinUpdate(this.step, clock.nowMicros(), this.mapEvery)
      onUpdate({
        maps: payload.maps, poses: payload.poses, anchors: payload.anchors,
        provenance: this.provenance,
        detail: `simulated twin feed · step ${this.step}`,
      })
    }
    tick()
    this.timer = setInterval(tick, this.intervalMs)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }
}

/** Read-only client for the documented twin feed endpoint
 * (integration request — backend pending). GETs
 * `{maps?, poses?, anchors?}` contract payloads. Transport failures
 * keep the last good snapshot; map/pose staleness is computed
 * downstream from payload timestamps. */
export class HttpTwinTransport implements TwinFeedTransport {
  private timer: ReturnType<typeof setInterval> | null = null

  constructor(
    private url: string,
    private pollMs = 2000,
    private fetchImpl: typeof fetch = fetch.bind(globalThis),
  ) {}

  start(onUpdate: (u: TwinFeedUpdate) => void, _clock?: { nowMicros(): number }): void {
    this.stop()
    const poll = async () => {
      try {
        const res = await this.fetchImpl(this.url, {
          headers: { accept: 'application/json' },
          signal: AbortSignal.timeout(5000),
        })
        if (!res.ok) return
        const body = await res.json() as Record<string, unknown>
        const asArray = (v: unknown) => (Array.isArray(v) ? v : v === undefined || v === null ? [] : [v])
        // Transport-level provenance: honor an explicit body label
        // (LIVE|REPLAY|DEMO); default LIVE only for unlabeled endpoints.
        // Per-payload labels inside maps/poses still override downstream.
        const bodyProv = body.provenance
        onUpdate({
          maps: asArray(body.maps ?? body.occupancy ?? body.occupancy_grid),
          poses: asArray(body.poses ?? body.pose_reports),
          anchors: asArray(body.anchors ?? body.registered_devices),
          provenance: bodyProv === 'LIVE' || bodyProv === 'REPLAY' || bodyProv === 'DEMO'
            ? bodyProv : 'LIVE',
          detail: `twin feed ${this.url}`,
        })
      } catch { /* keep last good snapshot; staleness flags downstream */ }
    }
    void _clock
    void poll()
    this.timer = setInterval(() => void poll(), this.pollMs)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }
}
