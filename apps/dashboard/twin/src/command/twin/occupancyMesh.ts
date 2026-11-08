import {
  CELL_OCCUPIED, CELL_UNKNOWN, frameToFacility, registerFrame,
  type ParsedOccupancyGrid,
} from './occupancyContract'
import type { TwinAnchor, TwinOccupancyMap } from '../model'

/**
 * Occupancy-grid -> 3D instance planning. Pure functions + one small
 * stateful slot allocator — no three.js imports, fully testable in
 * node. The React layer (TwinScene) binds the resulting instance
 * specs to InstancedMesh buffers.
 *
 * HEIGHTS ARE INFERRED, NEVER MEASURED. `inferredRectHeight` derives a
 * deterministic presentation height from the rect identity so the same
 * map revision always produces the same geometry — it is a visual aid
 * for "something occupies this volume", NOT a LiDAR or surveyed
 * measurement. The UI must keep labelling it as inferred.
 */

export interface OccupancyRect {
  /** Cell coords, x1/y1 exclusive. */
  x0: number; y0: number; x1: number; y1: number
}

/** Greedy maximal-rectangle merge: row runs extended while the x-span
 * is unchanged. Deterministic — identical grids always produce
 * identical rect lists in row-major discovery order. */
export function mergeCellRects(
  width: number, height: number,
  wanted: (ix: number, iy: number) => boolean,
): OccupancyRect[] {
  const rects: OccupancyRect[] = []
  let active = new Map<string, OccupancyRect>()
  for (let iy = 0; iy < height; iy += 1) {
    const next = new Map<string, OccupancyRect>()
    let ix = 0
    while (ix < width) {
      if (!wanted(ix, iy)) { ix += 1; continue }
      let x1 = ix + 1
      while (x1 < width && wanted(x1, iy)) x1 += 1
      const key = `${ix}:${x1}`
      const prev = active.get(key)
      if (prev) {
        prev.y1 = iy + 1
        next.set(key, prev)
      } else {
        const rect = { x0: ix, y0: iy, x1, y1: iy + 1 }
        rects.push(rect)
        next.set(key, rect)
      }
      ix = x1
    }
    active = next
  }
  return rects
}

/** FNV-1a -> [0, 1). Stable across runs/platforms (no Math.random). */
function hash01(text: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return (h >>> 0) / 0x100000000
}

/** Deterministic INFERRED presentation height (metres). Thin rects
 * (<= 2 cells across) read as walls (~0.8-1.3 m); bulkier rects read as
 * furniture/obstacles (~0.35-0.85 m). NOT a measurement — see header. */
export function inferredRectHeight(rect: OccupancyRect, frameId: string): number {
  const thin = Math.min(rect.x1 - rect.x0, rect.y1 - rect.y0) <= 2
  const h = hash01(`twin-h|${frameId}|${rect.x0},${rect.y0},${rect.x1},${rect.y1}`)
  const height = thin ? 0.8 + h * 0.5 : 0.35 + h * 0.5
  return Math.round(height * 100) / 100
}

export type TwinInstanceKind = 'occupied' | 'unknown'

/** One render instance: an axis-aligned world-space box. World frame is
 * three.js (map +x -> +X, map +y -> -Z, +Y up); cx/cy/cz is the box
 * centre, s* the full extents. */
export interface TwinInstance {
  /** Stable identity — unchanged rects keep their key across revisions
   * so the renderer can update only what changed. */
  key: string
  kind: TwinInstanceKind
  cx: number; cy: number; cz: number
  sx: number; sy: number; sz: number
}

const UNKNOWN_PLATE_HEIGHT = 0.015

function rectToInstance(
  rect: OccupancyRect, kind: TwinInstanceKind,
  map: TwinOccupancyMap,
): TwinInstance {
  const { resolutionM: res, origin } = map
  // origin is already facility-frame (registration applied upstream);
  // map +y becomes world -Z via cz negation.
  const fx0 = origin.x + rect.x0 * res
  const fx1 = origin.x + rect.x1 * res
  const fy0 = origin.y + rect.y0 * res
  const fy1 = origin.y + rect.y1 * res
  const sx = fx1 - fx0
  const sz = fy1 - fy0
  if (kind === 'occupied') {
    const sy = inferredRectHeight(rect, map.frameId)
    return {
      key: `occ:${map.frameId}:${rect.x0},${rect.y0},${rect.x1},${rect.y1}`,
      kind, cx: (fx0 + fx1) / 2, cy: sy / 2, cz: -(fy0 + fy1) / 2,
      sx, sy, sz,
    }
  }
  return {
    key: `unk:${map.frameId}:${rect.x0},${rect.y0},${rect.x1},${rect.y1}`,
    kind, cx: (fx0 + fx1) / 2, cy: UNKNOWN_PLATE_HEIGHT / 2, cz: -(fy0 + fy1) / 2,
    sx, sy: UNKNOWN_PLATE_HEIGHT, sz,
  }
}

export interface TwinInstancePlan {
  occupied: TwinInstance[]
  unknown: TwinInstance[]
}

/** Plan render instances for one map revision. Unknown cells become
 * low ground plates (unmapped != free); free cells render nothing —
 * the facility floor shows through. */
export function planTwinInstances(map: TwinOccupancyMap): TwinInstancePlan {
  const { width, height, cells } = map
  const occupiedRects = mergeCellRects(width, height, (ix, iy) => cells[iy * width + ix] === CELL_OCCUPIED)
  const unknownRects = mergeCellRects(width, height, (ix, iy) => cells[iy * width + ix] === CELL_UNKNOWN)
  return {
    occupied: occupiedRects.map(r => rectToInstance(r, 'occupied', map)),
    unknown: unknownRects.map(r => rectToInstance(r, 'unknown', map)),
  }
}

// ---------------------------------------------------------------------------
// Incremental slot allocation. Instances keep a stable slot keyed by
// rect identity; a revision that changes a few cells rewrites only the
// affected slots. `null` instance = clear the slot (zero-scale matrix).
// ---------------------------------------------------------------------------

export interface InstanceWrite {
  slot: number
  instance: TwinInstance | null
}

export class OccupancyInstanceSet {
  private readonly slots = new Map<string, number>()
  private specs: (TwinInstance | null)[] = []
  private free: number[] = []

  constructor(readonly kind: TwinInstanceKind) {}

  get size(): number { return this.slots.size }

  /** Apply the next plan; returns buffer writes + required instance
   * count. Unchanged specs produce no writes. */
  update(next: readonly TwinInstance[]): { count: number; writes: InstanceWrite[] } {
    const writes: InstanceWrite[] = []
    const wanted = new Set<string>()
    for (const inst of next) {
      if (inst.kind !== this.kind) continue
      wanted.add(inst.key)
    }
    // Release slots whose key disappeared.
    for (const [key, slot] of [...this.slots]) {
      if (!wanted.has(key)) {
        this.slots.delete(key)
        this.specs[slot] = null
        this.free.push(slot)
        writes.push({ slot, instance: null })
      }
    }
    for (const inst of next) {
      if (inst.kind !== this.kind) continue
      let slot = this.slots.get(inst.key)
      if (slot === undefined) {
        slot = this.free.pop() ?? this.specs.length
        if (slot >= this.specs.length) this.specs.length = slot + 1
        this.slots.set(inst.key, slot)
      }
      const prev = this.specs[slot]
      const changed = !prev
        || prev.cx !== inst.cx || prev.cy !== inst.cy || prev.cz !== inst.cz
        || prev.sx !== inst.sx || prev.sy !== inst.sy || prev.sz !== inst.sz
      if (changed) {
        this.specs[slot] = inst
        writes.push({ slot, instance: inst })
      }
    }
    return { count: this.specs.length, writes }
  }

  /** Drop everything (frame change / map removal). */
  clear(): InstanceWrite[] {
    const writes: InstanceWrite[] = []
    for (const slot of this.slots.values()) writes.push({ slot, instance: null })
    this.slots.clear()
    this.specs = []
    this.free = []
    return writes
  }
}

/** Contract -> registered TwinOccupancyMap. Registration is applied to
 * the origin so all downstream geometry is facility-frame. */
export function contractToTwinMap(
  grid: ParsedOccupancyGrid,
  provenance: TwinOccupancyMap['provenance'],
  elapsed: number,
  backendNowMicros: number,
): { map: TwinOccupancyMap; anchors: TwinAnchor[] } {
  const reg = registerFrame(grid.frameId)
  const registered = reg.kind !== 'unregistered'
  const origin = frameToFacility(grid.origin, grid.frameId) ?? { ...grid.origin }
  const at = grid.timestampMicros
    ? elapsed - Math.max(0, (backendNowMicros - grid.timestampMicros) / 1_000_000)
    : elapsed
  const stale = backendNowMicros > 0 && grid.timestampMicros > 0
    ? (backendNowMicros - grid.timestampMicros) / 1_000_000 > TWIN_MAP_STALE_S
    : false
  const map: TwinOccupancyMap = {
    frameId: grid.frameId,
    revision: grid.revision,
    resolutionM: grid.resolutionM,
    origin,
    width: grid.width,
    height: grid.height,
    timestampMicros: grid.timestampMicros,
    provenance,
    registered,
    registration: reg.kind,
    cells: grid.cells,
    unknown: grid.counts.unknown,
    free: grid.counts.free,
    occupied: grid.counts.occupied,
    stale,
    ageSeconds: Math.max(0, elapsed - at),
  }
  const anchors = grid.anchors.flatMap(a => {
    const p = frameToFacility({ x: a.x, y: a.y }, grid.frameId)
    if (!p) return []
    const anchor: TwinAnchor = { id: a.id, x: p.x, y: p.y, frameId: grid.frameId }
    if (a.label) anchor.label = a.label
    return [anchor]
  })
  return { map, anchors }
}

/** Maps publish far slower than pose fixes; 30 s without a newer
 * revision flags the layer stale in the UI. */
export const TWIN_MAP_STALE_S = 30
