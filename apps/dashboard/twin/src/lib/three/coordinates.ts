export interface MapPoint { x: number; y: number }
export interface MapFrame { origin: MapPoint; metersPerUnit: number }
export const METRIC_FRAME: MapFrame = { origin: { x: 0, y: 0 }, metersPerUnit: 1 }

function validate(frame: MapFrame, ...values: number[]) {
  if (![frame.origin.x, frame.origin.y, frame.metersPerUnit, ...values].every(Number.isFinite) || frame.metersPerUnit <= 0) {
    throw new Error('Coordinates must be finite and metersPerUnit must be positive')
  }
}

/** Right-handed Y-up world: map +x → world +X, map +y → world -Z; height is meters. */
export function mapToWorld(point: MapPoint, height = 0, frame = METRIC_FRAME): [number, number, number] {
  validate(frame, point.x, point.y, height)
  return [(point.x - frame.origin.x) * frame.metersPerUnit, height, -(point.y - frame.origin.y) * frame.metersPerUnit]
}

export function wallFromEndpoints(start: MapPoint, end: MapPoint, height = 2, thickness = 0.06, frame = METRIC_FRAME) {
  validate(frame, start.x, start.y, end.x, end.y, height, thickness)
  const length = Math.hypot(end.x - start.x, end.y - start.y) * frame.metersPerUnit
  if (length === 0 || height <= 0 || thickness <= 0) throw new Error('Wall dimensions must be positive')
  return {
    position: mapToWorld({ x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 }, height / 2, frame),
    size: [length, height, thickness] as [number, number, number],
    rotation: [0, Math.atan2(end.y - start.y, end.x - start.x), 0] as [number, number, number],
  }
}
