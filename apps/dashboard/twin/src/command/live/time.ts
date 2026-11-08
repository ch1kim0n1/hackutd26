/** Backend timestamp (SpacetimeDB t.timestamp() → epoch micros, possibly
 * bigint / number / Timestamp wrapper) → plain micros number. */
export function toMicros(value: unknown): number {
  if (value === null || value === undefined) return 0
  if (typeof value === 'bigint') return Number(value)
  if (typeof value === 'number') {
    // Heuristic: micros are ~1e15+; millis ~1e12; seconds ~1e9.
    if (value > 1e14) return value
    if (value > 1e11) return value * 1000
    return value * 1_000_000
  }
  const inner = (value as { microsSinceUnixEpoch?: unknown }).microsSinceUnixEpoch
  if (inner !== undefined) return toMicros(inner)
  const ms = (value as { toDate?: () => Date }).toDate?.()
  if (ms instanceof Date) return ms.getTime() * 1000
  return 0
}

/** Map a backend timestamp to CommandState elapsed-seconds.
 * `elapsedNow` is the live clock's current value; `backendNowMicros`
 * is the newest backend timestamp observed. Ages are real: as both
 * clocks advance together the mapped `at` stays fixed. */
export function backendToElapsed(
  micros: number, elapsedNow: number, backendNowMicros: number,
): number {
  if (!backendNowMicros || !micros) return elapsedNow
  const ageSeconds = (backendNowMicros - micros) / 1_000_000
  return elapsedNow - Math.max(0, ageSeconds)
}
