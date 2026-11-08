import { readLiveConfig, liveConfigProblems, type LiveConfig } from './config'
import { ApiClient } from './api'
import { SpaceTimeTransport } from './spacetime'
import { SimTwinTransport, HttpTwinTransport, type TwinFeedTransport } from './twin'
import { type LiveSyncDeps } from './sync'

export { LiveSync } from './sync'
export type { LivePhase } from './sync'
export { readLiveConfig, liveConfigProblems }
export type { LiveConfig } from './config'
export { mapSnapshot } from './map'
export { fixtureSnapshot } from './fixture'
export { mapTwinFeed, SimTwinTransport, HttpTwinTransport } from './twin'
export type { TwinFeedTransport, TwinPoseFix } from './twin'
export {
  OCCUPANCY_GRID_CONTRACT, POSE_REPORT_CONTRACT, parseOccupancyGrid,
  parsePoseReport, registerFrame, frameToFacility,
} from '../twin/occupancyContract'
export { planTwinInstances, mergeCellRects, inferredRectHeight, OccupancyInstanceSet } from '../twin/occupancyMesh'
export { simOccupancyContract, simPoseReport, simTwinUpdate, simAnchors } from '../twin/simFeed'
export type { LiveSnapshot, LiveRows, ApiSnapshot, TwinFeedUpdate } from './types'
export { toMicros, backendToElapsed } from './time'

/** Build the live-sync dependency graph for the current env config.
 * Fixture mode swaps both transports for the replay fixture. */
export function createLiveDeps(cfg: LiveConfig = readLiveConfig()): { deps: LiveSyncDeps; problems: string[] } {
  const problems = liveConfigProblems(cfg)
  const twin = createTwinTransport(cfg)
  if (cfg.transport === 'fixture') {
    // Fixture replay always carries the simulated twin feed so the
    // spatial pipeline is exercised end-to-end offline (REPLAY-labelled).
    return { deps: { fixture: true, pollMs: cfg.apiPollMs, twin: twin ?? new SimTwinTransport(600, 'REPLAY') }, problems: [] }
  }
  const spacetime = new SpaceTimeTransport(cfg.spacetimeUri, cfg.spacetimeToken, cfg.database)
  const api = new ApiClient(cfg.apiBase)
  return {
    deps: { rows: spacetime, api, pollMs: cfg.apiPollMs, twin: twin ?? undefined },
    problems,
  }
}

function createTwinTransport(cfg: LiveConfig): TwinFeedTransport | null {
  if (cfg.twinSim) return new SimTwinTransport(600, 'DEMO')
  if (cfg.twinFeedUrl) return new HttpTwinTransport(cfg.twinFeedUrl, cfg.twinPollMs)
  return null
}
