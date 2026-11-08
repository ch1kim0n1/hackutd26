import {
  CELL_FREE, CELL_OCCUPIED, CELL_UNKNOWN, OCCUPANCY_GRID_CONTRACT,
  POSE_REPORT_CONTRACT, TWIN_CONTRACT_SCHEMA_VERSION,
  type OccupancyAnchor,
} from './occupancyContract'
import { createFacilityGrid } from './occupancy'

/**
 * Deterministic simulated twin feeds — occupancy grids, pose reports
 * and registered anchors emitted as contract payloads before any
 * physical hardware/backend transport exists. Used by the fixture
 * transport, `?twin=sim`, demo mode, and tests. Everything produced
 * here is synthetic: callers must label it DEMO/REPLAY, never LIVE.
 */

export const SIM_MAP_FRAME = 'surveyed_floorplan'
export const SIM_POSE_FRAME = 'autonomy_map'
export const SIM_DEVICE_ID = 'rover-01'

/** Facility-matched sim map: 96x72 cells @ 0.25 m = the demo facility
 * footprint, so simulated geometry overlays the twin cleanly. Derived
 * from createFacilityGrid() so walls/doors match the static demo. */
export function simOccupancyCells(step: number): {
  width: number; height: number; resolutionM: number; origin: { x: number; y: number }
  cells: number[]
} {
  const grid = createFacilityGrid()
  const { width, height, resolution, cells } = grid
  const out = new Array<number>(width * height)
  // Scan frontier: cells ahead of the frontier column stay UNKNOWN
  // until the simulated scan reaches them — exercises incremental
  // reveal + unknown-cell rendering. Frontier sweeps left->right and
  // wraps, ~4 cells per revision.
  const frontier = (step * 4) % (width + 24)
  for (let iy = 0; iy < height; iy += 1) {
    for (let ix = 0; ix < width; ix += 1) {
      const idx = iy * width + ix
      const wall = cells[idx] === 1 ? CELL_OCCUPIED : CELL_FREE
      const unrevealed = ix > frontier
      // Dynamic obstacle: a small cart block patrols the ops floor.
      const cartX = 60 + Math.floor(Math.sin(step * 0.7) * 8)
      const cartY = 20 + Math.floor((Math.cos(step * 0.9) + 1) * 6)
      const cart = Math.abs(ix - cartX) <= 2 && Math.abs(iy - cartY) <= 2
      out[idx] = cart ? CELL_OCCUPIED : unrevealed ? CELL_UNKNOWN : wall
    }
  }
  return { width, height, resolutionM: resolution, origin: { ...grid.origin }, cells: out }
}

export function simOccupancyContract(step: number, nowMicros: number): Record<string, unknown> {
  const { width, height, resolutionM, origin, cells } = simOccupancyCells(step)
  return {
    contract: OCCUPANCY_GRID_CONTRACT,
    schema_version: TWIN_CONTRACT_SCHEMA_VERSION,
    frame_id: SIM_MAP_FRAME,
    resolution_m: resolutionM,
    width,
    height,
    origin,
    revision: step,
    timestamp: new Date(nowMicros / 1000).toISOString(),
    cells,
    anchors: simAnchors(),
  }
}

/** Registered surveyed positions for edge devices (puck/Pi-class
 * units) — the "registered Pi positions" layer. Coordinates are in
 * surveyed_floorplan metres, matching the sim map frame. */
export function simAnchors(): OccupancyAnchor[] {
  return [
    { id: 'puck-a-01', x: 3, y: 3, label: 'PUCK-A-01' },
    { id: 'puck-b-01', x: 20, y: 16, label: 'PUCK-B-01' },
    { id: 'pi-rover-01', x: 18, y: 3, label: 'PI / ROVER' },
    { id: 'pi-edge-01', x: 21, y: 6, label: 'PI-EDGE-01' },
  ]
}

/** Simulated pose report in autonomy_map frame (small room coords —
 * the frame offset is applied downstream, same as real sim_bridge
 * poses). */
export function simPoseReport(step: number, nowMicros: number): Record<string, unknown> {
  const t = step * 0.5
  return {
    contract: POSE_REPORT_CONTRACT,
    schema_version: TWIN_CONTRACT_SCHEMA_VERSION,
    device_id: SIM_DEVICE_ID,
    x: Math.sin(t * 0.35) * 6,
    y: Math.cos(t * 0.22) * 4,
    theta: t * 0.35 + Math.PI / 2,
    unit: 'm',
    frame_id: SIM_POSE_FRAME,
    timestamp: new Date(nowMicros / 1000).toISOString(),
    provenance: 'SIM',
  }
}

/** One simulated feed tick: latest map revision (every `mapEvery`
 * steps) plus a fresh pose report. */
export function simTwinUpdate(
  step: number, nowMicros: number, mapEvery = 3,
): { maps: Record<string, unknown>[]; poses: Record<string, unknown>[]; anchors: OccupancyAnchor[] } {
  return {
    maps: step % mapEvery === 0 ? [simOccupancyContract(step, nowMicros)] : [],
    poses: [simPoseReport(step, nowMicros)],
    anchors: simAnchors(),
  }
}
