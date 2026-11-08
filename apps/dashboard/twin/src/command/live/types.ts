import type {
  AgentRecord, Approval, CommandEvent, Device, Evidence, Finding,
  Incident, Mission, Observation, Rover, TelemetrySample, TwinFeedState, Zone,
} from '../model'
import type {
  Actions, Alerts, Assets, AuditEvents, Approvals, Devices,
  Evidence as StEvidence, Health, Incidents, Missions, Observations,
  RfFrames, ScopeEntries, Zones,
} from '../../spacetimedb/types'

/** Raw rows collected from SpacetimeDB role-scoped views. Plain data —
 * transports decode SDK types before handing them here. */
export interface LiveRows {
  zones: Zones[]
  devices: Devices[]
  assets: Assets[]
  observations: Observations[]
  incidents: Incidents[]
  evidence: StEvidence[]
  missions: Missions[]
  approvals: Approvals[]
  actions: Actions[]
  scopeEntries: ScopeEntries[]
  alerts: Alerts[]
  auditEvents: AuditEvents[]
  health: Health[]
  rfFrames: RfFrames[]
}

export function emptyRows(): LiveRows {
  return {
    zones: [], devices: [], assets: [], observations: [], incidents: [],
    evidence: [], missions: [], approvals: [], actions: [],
    scopeEntries: [], alerts: [], auditEvents: [], health: [], rfFrames: [],
  }
}

/** One investigation run from the Python API facade (issue #96). The
 * API keeps its own incident-workflow store — these records feed the
 * agent activity stream only; they are never merged into the
 * SpacetimeDB incident lists (separate universe, documented). */
export interface ApiInvestigation {
  incident_id: string
  by: string
  brief: string
  run_index: number
  assessment: {
    title?: string; severity?: string; confidence?: number
    summary?: string; requestIsolation?: boolean
  }
}

export interface ApiSnapshot {
  reachable: boolean
  detail: string
  investigations: ApiInvestigation[]
  incidentCount: number | null
}

/** Raw twin spatial payloads from a dedicated feed transport (sim or a
 * documented backend endpoint). Payloads are UNVALIDATED contract
 * candidates — map.ts parses/validates them like observation-embedded
 * contracts. */
export interface TwinFeedUpdate {
  maps: unknown[]
  poses: unknown[]
  anchors: unknown[]
  provenance: 'LIVE' | 'REPLAY' | 'DEMO'
  detail: string
}

export interface LiveSnapshot {
  /** 'LIVE' for real backends, 'REPLAY' for recorded fixtures — never
   * conflated (docs/13 provenance vocabulary). */
  provenance: 'LIVE' | 'REPLAY'
  rows: LiveRows
  api: ApiSnapshot
  /** Newest backend timestamp seen (epoch micros) — anchors the
   * backend-time → simulation-elapsed mapping. */
  backendNowMicros: number
  /** Latest dedicated twin feed update, when a transport is configured. */
  twin?: TwinFeedUpdate
}

/** The entity collections a live snapshot owns outright. */
export interface LiveEntities {
  zones: Zone[]
  devices: Device[]
  observations: Observation[]
  incidents: Incident[]
  evidence: Evidence[]
  findings: Finding[]
  missions: Mission[]
  approvals: Approval[]
  events: CommandEvent[]
  activity: AgentRecord[]
  telemetry: TelemetrySample[]
  rover: Rover
  twinFeed: TwinFeedState
}
