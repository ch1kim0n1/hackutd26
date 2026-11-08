import type { ApiInvestigation, ApiSnapshot } from './types'

/** Minimal FastAPI facade client (issue #96 surface). Read-only — the
 * live dashboard consumes health, readiness, investigations, and an
 * incident count for status. Bearer auth is optional in dev (the
 * facade accepts unauthenticated reads for observer-level data). */
export class ApiClient {
  constructor(private base: string, private fetchImpl: typeof fetch = fetch.bind(globalThis)) {}

  private async get<T>(path: string): Promise<T> {
    const res = await this.fetchImpl(`${this.base}${path}`, {
      headers: { accept: 'application/json' },
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok) throw new Error(`API ${path} → HTTP ${res.status}`)
    return res.json() as Promise<T>
  }

  async snapshot(): Promise<ApiSnapshot> {
    const unreachable: ApiSnapshot = { reachable: false, detail: 'unreachable', investigations: [], incidentCount: null }
    try {
      const [health, ready, investigations, incidents] = await Promise.all([
        this.get<{ status?: string }>('/healthz'),
        this.get<{ status?: string }>('/readyz'),
        this.get<{ items?: ApiInvestigation[] } | ApiInvestigation[]>('/investigations'),
        this.get<{ items?: unknown[] } | unknown[]>('/incidents'),
      ])
      const invList = Array.isArray(investigations) ? investigations : investigations.items ?? []
      const incList = Array.isArray(incidents) ? incidents : incidents.items ?? []
      const ok = health.status === 'ok' && ready.status === 'ready'
      return {
        reachable: ok,
        detail: ok ? `API live · ${incList.length} incidents · ${invList.length} investigations` : `API degraded (${health.status}/${ready.status})`,
        investigations: invList.slice(-40),
        incidentCount: incList.length,
      }
    } catch (error) {
      return { ...unreachable, detail: `API unreachable: ${error instanceof Error ? error.message : String(error)}` }
    }
  }
}
