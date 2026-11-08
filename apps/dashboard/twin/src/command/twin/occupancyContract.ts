import type { Point } from '../model'
import { toMicros } from '../live/time'

/**
 * Versioned twin spatial contracts (docs/13 §9 — proposed, frontend
 * implemented; backend transport is a documented integration request).
 *
 * `sentinel.rover.occupancy_grid` v1 — ROS OccupancyGrid-aligned cell
 * semantics: -1 unknown, 0 free, 100 occupied (values between are
 * occupancy probability, classified at the 50 threshold). `cells` is
 * row-major, `cells[iy * width + ix]`; `origin` is the frame_id-space
 * coordinate of the lower-left corner of cell (0,0); cell (ix,iy)
 * covers [origin.x + ix*res, origin.x + (ix+1)*res) x
 * [origin.y + iy*res, origin.y + (iy+1)*res). `frame_id`, `revision`
 * (monotonic per frame), and `timestamp` version each snapshot.
 *
 * `sentinel.rover.pose_report` v1 — rover pose: x, y (metres unless
 * unit 'mm'), theta (radians, map-frame CCW from +x), timestamp,
 * frame_id, optional provenance.
 *
 * Cell-scale normalization: the contract is -1/0..100. If every cell
 * value lies in [-1, 1] the array is treated as normalized 0..1
 * probability (legacy producers) and scaled x100 before
 * classification — documented, deterministic, and identical for the
 * existing 0..1 demo grid (threshold 0.5 == 50).
 */

export const OCCUPANCY_GRID_CONTRACT = 'sentinel.rover.occupancy_grid'
export const POSE_REPORT_CONTRACT = 'sentinel.rover.pose_report'
export const TWIN_CONTRACT_SCHEMA_VERSION = 1

export const OCCUPIED_THRESHOLD = 50
export const CELL_UNKNOWN = -1
export const CELL_FREE = 0
export const CELL_OCCUPIED = 100

/** Hard limits so a malformed/hostile payload cannot allocate unbounded
 * geometry. 512x512 cells at 1 m is already far larger than any lab map. */
export const MAX_GRID_DIM = 512
export const MAX_GRID_CELLS = 262_144
export const MAX_MAP_EXTENT_M = 500

export class TwinContractError extends Error {}

export interface OccupancyAnchor {
  id: string
  x: number
  y: number
  label?: string
}

export interface ParsedOccupancyGrid {
  contract: typeof OCCUPANCY_GRID_CONTRACT
  schemaVersion: 1
  frameId: string
  resolutionM: number
  width: number
  height: number
  /** frame_id-space coords of cell (0,0)'s lower-left corner. */
  origin: Point
  revision: number
  timestampMicros: number
  /** Normalized cells: exactly -1 (unknown), 0 (free), or 100 (occupied). */
  cells: Int8Array
  anchors: OccupancyAnchor[]
  counts: { unknown: number; free: number; occupied: number }
}

export interface ParsedPoseReport {
  contract: typeof POSE_REPORT_CONTRACT
  schemaVersion: 1
  deviceId: string
  x: number
  y: number
  /** Heading in radians, CCW from frame +x (map convention). */
  theta: number
  frameId: string
  timestampMicros: number
  unit: 'm' | 'mm'
  provenance?: string
}

function fail(reason: string): never {
  throw new TwinContractError(reason)
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

function finite(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

function boundedString(v: unknown, field: string, max = 128): string {
  if (typeof v !== 'string' || v.trim().length === 0 || v.length > max) fail(`${field} must be a non-empty string <= ${max} chars`)
  return v
}

/** ISO-8601 or epoch (s/ms/us heuristic, same as live/time.ts). */
export function contractTimestampMicros(value: unknown): number {
  if (typeof value === 'string' && value.trim().length > 0) {
    const ms = Date.parse(value)
    if (!Number.isNaN(ms)) return ms * 1000
    const n = Number(value)
    if (Number.isFinite(n)) return toMicros(n)
    fail('timestamp is not a parseable ISO-8601 string or epoch number')
  }
  if (finite(value)) return toMicros(value)
  fail('timestamp must be an ISO-8601 string or epoch number')
}

function parsePoint(v: unknown, field: string): Point {
  if (!isRecord(v) || !finite(v.x) || !finite(v.y)) fail(`${field} must be an object with finite x and y`)
  return { x: v.x as number, y: v.y as number }
}

function parseAnchors(v: unknown): OccupancyAnchor[] {
  if (v === undefined || v === null) return []
  if (!Array.isArray(v) || v.length > 512) fail('anchors must be an array of <= 512 entries')
  return v.map((a, i) => {
    if (!isRecord(a)) fail(`anchors[${i}] must be an object`)
    const id = boundedString(a.id, `anchors[${i}].id`, 64)
    if (!finite(a.x) || !finite(a.y)) fail(`anchors[${i}] requires finite x and y`)
    const anchor: OccupancyAnchor = { id, x: a.x as number, y: a.y as number }
    if (typeof a.label === 'string' && a.label.length <= 64) anchor.label = a.label
    return anchor
  })
}

/** Classify raw contract cells into canonical -1 | 0 | 100.
 * Unit-scale detection: every value inside [-1, 1] means the producer
 * sent normalized 0..1 probabilities (or binary 0/1) — scale x100. */
export function normalizeOccupancyCells(raw: readonly number[]): Int8Array {
  const unitScale = raw.every(v => v >= -1 && v <= 1)
  const out = new Int8Array(raw.length)
  for (let i = 0; i < raw.length; i += 1) {
    const v = raw[i]
    if (v < 0) { out[i] = CELL_UNKNOWN; continue }
    const p = unitScale ? v * 100 : v
    out[i] = p >= OCCUPIED_THRESHOLD ? CELL_OCCUPIED : CELL_FREE
  }
  return out
}

export function parseOccupancyGrid(input: unknown): ParsedOccupancyGrid {
  if (!isRecord(input)) fail('occupancy grid must be an object')
  if (input.contract !== OCCUPANCY_GRID_CONTRACT) fail(`contract must be "${OCCUPANCY_GRID_CONTRACT}"`)
  if (input.schema_version !== TWIN_CONTRACT_SCHEMA_VERSION) fail(`schema_version must be ${TWIN_CONTRACT_SCHEMA_VERSION}`)
  const { width, height } = input
  if (!Number.isInteger(width) || !Number.isInteger(height) || (width as number) < 1 || (height as number) < 1) {
    fail('width and height must be positive integers')
  }
  if ((width as number) > MAX_GRID_DIM || (height as number) > MAX_GRID_DIM || (width as number) * (height as number) > MAX_GRID_CELLS) {
    fail(`grid exceeds limits (max ${MAX_GRID_DIM}x${MAX_GRID_DIM}, ${MAX_GRID_CELLS} cells)`)
  }
  const resolutionM = input.resolution_m
  if (!finite(resolutionM) || resolutionM <= 0) fail('resolution_m must be a positive finite number')
  const origin = parsePoint(input.origin, 'origin')
  const extent = Math.max((width as number) * resolutionM, (height as number) * resolutionM)
  if (extent > MAX_MAP_EXTENT_M) fail(`map extent ${extent} m exceeds ${MAX_MAP_EXTENT_M} m`)
  const frameId = boundedString(input.frame_id, 'frame_id')
  const revision = input.revision
  if (!Number.isSafeInteger(revision) || (revision as number) < 0) fail('revision must be a non-negative safe integer')
  const timestampMicros = contractTimestampMicros(input.timestamp)
  const rawCells = input.cells
  if (!Array.isArray(rawCells) && !(rawCells instanceof Int8Array) && !(rawCells instanceof Int16Array) && !(rawCells instanceof Uint8Array)) {
    fail('cells must be an array of occupancy values')
  }
  const cellCount = (width as number) * (height as number)
  if (rawCells.length !== cellCount) fail(`cells length ${rawCells.length} != width*height ${cellCount}`)
  const numeric: number[] = new Array<number>(cellCount)
  for (let i = 0; i < cellCount; i += 1) {
    const v = (rawCells as ArrayLike<number>)[i]
    if (!finite(v) || v < -1 || v > 100) fail(`cells[${i}] must be a finite value in [-1, 100]`)
    numeric[i] = v
  }
  const cells = normalizeOccupancyCells(numeric)
  const counts = { unknown: 0, free: 0, occupied: 0 }
  for (let i = 0; i < cellCount; i += 1) {
    if (cells[i] === CELL_UNKNOWN) counts.unknown += 1
    else if (cells[i] === CELL_OCCUPIED) counts.occupied += 1
    else counts.free += 1
  }
  return {
    contract: OCCUPANCY_GRID_CONTRACT, schemaVersion: 1, frameId,
    resolutionM, width: width as number, height: height as number,
    origin, revision: revision as number, timestampMicros, cells,
    anchors: parseAnchors(input.anchors), counts,
  }
}

export function parsePoseReport(input: unknown): ParsedPoseReport {
  if (!isRecord(input)) fail('pose report must be an object')
  if (input.contract !== POSE_REPORT_CONTRACT) fail(`contract must be "${POSE_REPORT_CONTRACT}"`)
  if (input.schema_version !== TWIN_CONTRACT_SCHEMA_VERSION) fail(`schema_version must be ${TWIN_CONTRACT_SCHEMA_VERSION}`)
  const deviceId = boundedString(input.device_id, 'device_id', 64)
  if (!finite(input.x) || !finite(input.y)) fail('x and y must be finite numbers')
  const theta = input.theta ?? input.heading_rad ?? input.yaw
  if (!finite(theta)) fail('theta must be a finite number (radians)')
  const frameId = boundedString(input.frame_id ?? input.frame, 'frame_id')
  const unit = input.unit === 'mm' ? 'mm' : 'm'
  const scale = unit === 'mm' ? 0.001 : 1
  const timestampMicros = contractTimestampMicros(input.timestamp)
  const out: ParsedPoseReport = {
    contract: POSE_REPORT_CONTRACT, schemaVersion: 1, deviceId,
    x: (input.x as number) * scale, y: (input.y as number) * scale,
    theta: theta as number, frameId, timestampMicros, unit,
  }
  if (typeof input.provenance === 'string' && input.provenance.length <= 16) out.provenance = input.provenance
  return out
}

// ---------------------------------------------------------------------------
// Frame registration — the only transforms the twin applies. Identity
// frames are already facility/surveyed metres; autonomy_map uses the
// documented static sim-room offset (docs/15). Anything else is
// UNREGISTERED: geometry is kept but flagged, never silently placed.
// ---------------------------------------------------------------------------

/** Documented static registration: autonomy sim room centred on the
 * facility (same transform live/map.ts applies to autonomy_map poses). */
export const AUTONOMY_MAP_OFFSET: Point = { x: 12, y: 9 }

export type FrameRegistrationKind = 'identity' | 'static-offset' | 'unregistered'

export interface FrameRegistration {
  kind: FrameRegistrationKind
  /** frame_id coords -> facility coords offset (metres, translation only). */
  offset: Point
  note: string
}

const FRAME_REGISTRY: Record<string, FrameRegistration> = {
  facility: { kind: 'identity', offset: { x: 0, y: 0 }, note: 'facility frame — already twin coordinates' },
  surveyed_floorplan: { kind: 'identity', offset: { x: 0, y: 0 }, note: 'surveyed floorplan — already twin coordinates' },
  floorplan: { kind: 'identity', offset: { x: 0, y: 0 }, note: 'surveyed floorplan — already twin coordinates' },
  autonomy_map: {
    kind: 'static-offset', offset: { ...AUTONOMY_MAP_OFFSET },
    note: 'approximate — sim room statically registered at facility centre; poses frames are never surveyed (docs/14)',
  },
}

export function registerFrame(frameId: string): FrameRegistration {
  return FRAME_REGISTRY[frameId] ?? {
    kind: 'unregistered', offset: { x: 0, y: 0 },
    note: `unregistered frame "${frameId}" — coordinates are not placed on the facility map`,
  }
}

/** frame_id coords -> facility coords, or null when unregistered. */
export function frameToFacility(point: Point, frameId: string): Point | null {
  const reg = registerFrame(frameId)
  if (reg.kind === 'unregistered') return null
  return { x: point.x + reg.offset.x, y: point.y + reg.offset.y }
}
