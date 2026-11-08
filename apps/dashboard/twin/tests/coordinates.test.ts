import { describe, expect, it } from 'vitest'
import { mapToWorld, wallFromEndpoints } from '../src/lib/three/coordinates'

describe('map → world convention', () => {
  it('transforms origin, scale, and height without confusing map Y with elevation', () => {
    expect(mapToWorld({ x: 14, y: 24 }, 1.7, { origin: { x: 10, y: 20 }, metersPerUnit: 0.5 })).toEqual([2, 1.7, -2])
  })
  it('places a north-running wall with local X aligned to world -Z', () => {
    const wall = wallFromEndpoints({ x: 0, y: 0 }, { x: 0, y: 4 })
    expect(wall.position).toEqual([0, 1, -2])
    expect(wall.size).toEqual([4, 2, 0.06])
    expect(wall.rotation[1]).toBeCloseTo(Math.PI / 2)
  })
  it('rejects invalid scales, nonfinite coordinates, and degenerate geometry', () => {
    expect(() => mapToWorld({ x: NaN, y: 1 })).toThrow()
    expect(() => mapToWorld({ x: 1, y: 1 }, 0, { origin: { x: 0, y: 0 }, metersPerUnit: 0 })).toThrow()
    expect(() => wallFromEndpoints({ x: 1, y: 1 }, { x: 1, y: 1 })).toThrow()
  })
})
