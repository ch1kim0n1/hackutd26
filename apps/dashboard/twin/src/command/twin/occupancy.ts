import type { Point } from '../model'

export interface OccupancyGrid {
  width: number
  height: number
  resolution: number
  origin: Point
  cells: readonly number[]
}
export interface OccupancyWall { id: string; start: Point; end: Point; thickness: number }

/** Merge adjoining occupied cells into horizontal runs. Map +y becomes world -Z. */
export function occupancyToWalls(grid: OccupancyGrid, threshold = 0.5): OccupancyWall[] {
  const { width, height, resolution, origin, cells } = grid
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || !Number.isFinite(resolution) || resolution <= 0 || !Number.isFinite(origin.x) || !Number.isFinite(origin.y) || cells.length !== width * height || !Number.isFinite(threshold)) {
    throw new Error('Invalid occupancy grid dimensions, resolution, origin, or threshold')
  }
  if (cells.some(value => !Number.isFinite(value))) throw new Error('Occupancy values must be finite')
  const walls: OccupancyWall[] = []
  for (let y = 0; y < height; y += 1) {
    let start = -1
    for (let x = 0; x <= width; x += 1) {
      const occupied = x < width && cells[y * width + x] >= threshold
      if (occupied && start < 0) start = x
      if (!occupied && start >= 0) {
        walls.push({
          id: `occupancy-${y}-${start}-${x}`,
          start: { x: origin.x + start * resolution, y: origin.y + (y + 0.5) * resolution },
          end: { x: origin.x + x * resolution, y: origin.y + (y + 0.5) * resolution },
          thickness: resolution,
        })
        start = -1
      }
    }
  }
  return walls
}

/** Deterministic 0.25 m map: perimeter and interior partitions include navigable doors. */
export function createFacilityGrid(): OccupancyGrid {
  const width = 96, height = 72, resolution = 0.25
  const cells = Array<number>(width * height).fill(0)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const perimeter = y === 0 || y === height - 1 || x === 0 || x === width - 1
      const verticalPartition = x === 56 && !(y >= 13 && y <= 23) && !(y >= 48 && y <= 57)
      const horizontalPartition = y === 36 && x > 56 && !(x >= 68 && x <= 79)
      cells[y * width + x] = perimeter || verticalPartition || horizontalPartition ? 1 : 0
    }
  }
  return { width, height, resolution, origin: { x: 0, y: 0 }, cells }
}

/** Convert the row runs to larger rectilinear wall prisms without changing occupied area. */
export function mergeCollinearWalls(walls: readonly OccupancyWall[]): OccupancyWall[] {
  const merged: OccupancyWall[] = []
  for (const wall of walls) {
    const existing = merged.find(candidate => candidate.start.x === wall.start.x && candidate.end.x === wall.end.x && Math.abs(candidate.end.y + candidate.thickness / 2 - (wall.start.y - wall.thickness / 2)) < 0.00001)
    if (existing && Math.abs(wall.end.x - wall.start.x - wall.thickness) < 0.00001) {
      const low = existing.start.y - existing.thickness / 2
      const high = wall.start.y + wall.thickness / 2
      existing.start.y = (low + high) / 2
      existing.end.y = (low + high) / 2
      existing.thickness = high - low
    } else {
      merged.push({ ...wall, start: { ...wall.start }, end: { ...wall.end } })
    }
  }
  return merged
}
