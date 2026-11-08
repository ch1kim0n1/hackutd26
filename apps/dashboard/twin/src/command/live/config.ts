/** Live-mode configuration. All values come from Vite env vars so no
 * secrets are committed; the SpacetimeDB identity token must be a
 * provisioned role token (see deploy/seeds + docs/07). */
export interface LiveConfig {
  /** SpacetimeDB HTTP endpoint, e.g. http://127.0.0.1:3000 */
  spacetimeUri: string
  database: string
  /** Provisioned identity token for a role that can read ops feeds
   * (admin recommended for the dashboard — sees all incidents). */
  spacetimeToken: string
  /** Python API facade base URL (issue #96), e.g. http://127.0.0.1:8000 */
  apiBase: string
  /** 'real' uses SpacetimeDB + FastAPI; 'fixture' replays recorded rows
   * labelled REPLAY (used by tests and offline demos). */
  transport: 'real' | 'fixture'
  /** Poll cadence for the API facade snapshot (ms). */
  apiPollMs: number
  /** Optional dedicated twin spatial feed endpoint (docs/13 §9 —
   * backend integration request). Empty disables the HTTP transport;
   * contract payloads embedded in observations are always consumed. */
  twinFeedUrl: string
  /** Poll cadence for the twin feed endpoint (ms). */
  twinPollMs: number
  /** Force the simulated twin feed even in 'real' transport
   * (?twin=sim) — for testing before hardware exists. */
  twinSim: boolean
}

export function readLiveConfig(env: Record<string, string | undefined> = import.meta.env as unknown as Record<string, string | undefined>): LiveConfig {
  // Runtime override for tests/demos: ?live=fixture forces the replay
  // transport regardless of build-time env.
  let transport: LiveConfig['transport'] = env.VITE_LIVE_TRANSPORT === 'fixture' ? 'fixture' : 'real'
  let twinSim = env.VITE_TWIN_SIM === '1'
  try {
    const q = new URLSearchParams(window.location.search)
    const live = q.get('live')
    if (live === 'fixture') transport = 'fixture'
    if (live === 'real') transport = 'real'
    if (q.get('twin') === 'sim') twinSim = true
    if (q.get('twin') === 'off') twinSim = false
  } catch { /* non-browser env */ }
  return {
    spacetimeUri: env.VITE_SPACETIMEDB_URI ?? 'http://127.0.0.1:3000',
    database: env.VITE_SPACETIMEDB_DATABASE ?? 'sentinel-hive',
    spacetimeToken: env.VITE_SPACETIMEDB_TOKEN ?? '',
    apiBase: env.VITE_API_BASE ?? 'http://127.0.0.1:8000',
    transport,
    apiPollMs: Number(env.VITE_API_POLL_MS ?? 5000) || 5000,
    twinFeedUrl: env.VITE_TWIN_FEED_URL ?? '',
    twinPollMs: Number(env.VITE_TWIN_POLL_MS ?? 2000) || 2000,
    twinSim,
  }
}

export function liveConfigProblems(cfg: LiveConfig): string[] {
  const problems: string[] = []
  if (!cfg.spacetimeToken) problems.push('VITE_SPACETIMEDB_TOKEN is not set — provision a role token (deploy/seeds/seed.ts writes deploy/secrets/identities.json)')
  if (!cfg.spacetimeUri) problems.push('VITE_SPACETIMEDB_URI is empty')
  if (!cfg.apiBase) problems.push('VITE_API_BASE is empty')
  return problems
}
