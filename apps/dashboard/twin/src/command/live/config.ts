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
}

export function readLiveConfig(env: Record<string, string | undefined> = import.meta.env as unknown as Record<string, string | undefined>): LiveConfig {
  // Runtime override for tests/demos: ?live=fixture forces the replay
  // transport regardless of build-time env.
  let transport: LiveConfig['transport'] = env.VITE_LIVE_TRANSPORT === 'fixture' ? 'fixture' : 'real'
  try {
    const q = new URLSearchParams(window.location.search).get('live')
    if (q === 'fixture') transport = 'fixture'
    if (q === 'real') transport = 'real'
  } catch { /* non-browser env */ }
  return {
    spacetimeUri: env.VITE_SPACETIMEDB_URI ?? 'http://127.0.0.1:3000',
    database: env.VITE_SPACETIMEDB_DATABASE ?? 'sentinel-hive',
    spacetimeToken: env.VITE_SPACETIMEDB_TOKEN ?? '',
    apiBase: env.VITE_API_BASE ?? 'http://127.0.0.1:8000',
    transport,
    apiPollMs: Number(env.VITE_API_POLL_MS ?? 5000) || 5000,
  }
}

export function liveConfigProblems(cfg: LiveConfig): string[] {
  const problems: string[] = []
  if (!cfg.spacetimeToken) problems.push('VITE_SPACETIMEDB_TOKEN is not set — provision a role token (deploy/seeds/seed.ts writes deploy/secrets/identities.json)')
  if (!cfg.spacetimeUri) problems.push('VITE_SPACETIMEDB_URI is empty')
  if (!cfg.apiBase) problems.push('VITE_API_BASE is empty')
  return problems
}
