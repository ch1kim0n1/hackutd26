import { readLiveConfig, liveConfigProblems, type LiveConfig } from './config'
import { ApiClient } from './api'
import { SpaceTimeTransport } from './spacetime'
import { type LiveSyncDeps } from './sync'

export { LiveSync } from './sync'
export type { LivePhase } from './sync'
export { readLiveConfig, liveConfigProblems }
export type { LiveConfig } from './config'
export { mapSnapshot } from './map'
export { fixtureSnapshot } from './fixture'
export type { LiveSnapshot, LiveRows, ApiSnapshot } from './types'
export { toMicros, backendToElapsed } from './time'

/** Build the live-sync dependency graph for the current env config.
 * Fixture mode swaps both transports for the replay fixture. */
export function createLiveDeps(cfg: LiveConfig = readLiveConfig()): { deps: LiveSyncDeps; problems: string[] } {
  const problems = liveConfigProblems(cfg)
  if (cfg.transport === 'fixture') {
    return { deps: { fixture: true, pollMs: cfg.apiPollMs }, problems: [] }
  }
  const spacetime = new SpaceTimeTransport(cfg.spacetimeUri, cfg.spacetimeToken, cfg.database)
  const api = new ApiClient(cfg.apiBase)
  return {
    deps: { rows: spacetime, api, pollMs: cfg.apiPollMs },
    problems,
  }
}
