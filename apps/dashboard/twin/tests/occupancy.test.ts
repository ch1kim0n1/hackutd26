import { describe, expect, it } from 'vitest'
import { createFacilityGrid, mergeCollinearWalls, occupancyToWalls } from '../src/command/twin/occupancy'

describe('occupancy geometry', () => {
  it('preserves metric coordinates and merges adjacent occupied cells into runs', () => {
    expect(occupancyToWalls({ width: 4, height: 2, resolution: 0.5, origin: { x: 3, y: 7 }, cells: [1, 1, 0, 1, 0, 0, 0, 0] })).toEqual([
      { id: 'occupancy-0-0-2', start: { x: 3, y: 7.25 }, end: { x: 4, y: 7.25 }, thickness: 0.5 },
      { id: 'occupancy-0-3-4', start: { x: 4.5, y: 7.25 }, end: { x: 5, y: 7.25 }, thickness: 0.5 },
    ])
  })
  it('preserves occupied map area when optimizing facility wall prisms', () => {
    const grid = createFacilityGrid()
    const raw = occupancyToWalls(grid)
    const walls = mergeCollinearWalls(raw)
    const area = walls.reduce((sum, wall) => sum + (wall.end.x - wall.start.x) * wall.thickness, 0)
    expect(area).toBeCloseTo(grid.cells.reduce((sum, cell) => sum + cell, 0) * grid.resolution ** 2)
    expect(walls.length).toBeLessThan(25)
    // Two gaps in the vertical divider remain open for patrol movement.
    expect(grid.cells[18 * grid.width + 56]).toBe(0)
    expect(grid.cells[52 * grid.width + 56]).toBe(0)
  })
  it('rejects malformed maps rather than silently inventing geometry', () => {
    expect(() => occupancyToWalls({ width: 2, height: 2, resolution: 1, origin: { x: 0, y: 0 }, cells: [1] })).toThrow()
    expect(() => occupancyToWalls({ width: 1, height: 1, resolution: 0, origin: { x: 0, y: 0 }, cells: [1] })).toThrow()
  })
})
