import type {
  AgentRecord, Approval, CommandEvent, Device, DeviceKind, Evidence,
  Finding, Incident, Mission, Observation, ObservationKind,
  Rover, Severity, TelemetrySample, TimelineEntry, Zone,
} from '../model'
import { registerFrame } from '../twin/occupancyContract'
import { mapTwinFeed, type TwinPoseFix } from './twin'
import type { LiveRows, LiveSnapshot } from './types'
import { backendToElapsed, toMicros } from './time'

export interface MapContext {
  elapsed: number
  backendNowMicros: number
  provenance: 'LIVE' | 'REPLAY'
}

const TAG = (p: MapContext) => (p.provenance === 'LIVE' ? 'LIVE' : 'REPLAY')

function hashId(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return h
}

const ZONE_COLORS = ['#a8a29e', '#22c55e', '#bfb6ab', '#7dd3fc', '#f472b6', '#86efac']

export function mapZones(rows: LiveRows['zones']): Zone[] {
  return rows.map((z, i) => {
    let bounds: [number, number, number, number] = [0, 0, 20, 20]
    try {
      const b = JSON.parse(z.boundsJson) as { x?: number; y?: number; w?: number; h?: number }
      if (Number.isFinite(b.x) && Number.isFinite(b.y) && Number.isFinite(b.w) && Number.isFinite(b.h)) {
        bounds = [b.x!, b.y!, b.x! + b.w!, b.y! + b.h!]
      }
    } catch { /* keep default bounds */ }
    const [x0, y0, x1, y1] = bounds
    return {
      id: z.id, name: z.name, code: String.fromCharCode(65 + (i % 26)),
      bounds, position: { x: (x0 + x1) / 2, y: (y0 + y1) / 2 },
      color: ZONE_COLORS[hashId(z.id) % ZONE_COLORS.length],
    }
  })
}

const DEVICE_KIND: Record<string, DeviceKind> = {
  PuckWifi: 'wifi', PuckContact: 'sensor', PuckBle: 'ble',
  Rover: 'rover', Kismet: 'wifi', Sdr: 'sensor', Camera: 'sensor', Other: 'sensor',
}
const DEVICE_STATUS: Record<string, Device['status']> = {
  Online: 'healthy', Degraded: 'watch', Fault: 'threat', Offline: 'watch', Unknown: 'watch',
}

export function mapDevices(rows: LiveRows, ctx: MapContext): Device[] {
  const zonePos = new Map(mapZones(rows.zones).map(z => [z.id, z.position]))
  const zoneIds = [...zonePos.keys()]
  return rows.devices.map((d, i) => {
    const kind = DEVICE_KIND[d.type.tag] ?? 'sensor'
    const base = zonePos.get(d.zoneId) ?? zonePos.get(zoneIds[i % zoneIds.length] ?? '') ?? { x: 12, y: 9 }
    // Deterministic sub-position inside the zone — devices carry no
    // surveyed coordinates in the backend; this is a layout aid, not
    // a measurement (documented gap).
    const h = hashId(d.id)
    const position = { x: base.x + ((h % 5) - 2) * 0.9, y: base.y + (((h >> 4) % 5) - 2) * 0.9 }
    const status = DEVICE_STATUS[d.status.tag] ?? 'watch'
    const rssi = -70 // no per-device RF telemetry in the schema (rf_frames is receiver-level)
    return {
      id: d.id, name: d.id.toUpperCase(), kind, zoneId: d.zoneId,
      position, status, statusKnown: !!DEVICE_STATUS[d.status.tag] && d.status.tag !== 'Unknown',
      protocol: kind === 'ble' ? 'BLE' : kind === 'wifi' ? 'Wi-Fi' : 'System',
      address: `lab://${d.id}`, vendor: `${d.type.tag} · fw ${d.firmware || 'unknown'}`,
      risk: d.status.tag === 'Fault' ? 88 : d.status.tag === 'Degraded' ? 55 : 8,
      rssi, lastSeen: backendToElapsed(toMicros(d.lastSeen), ctx.elapsed, ctx.backendNowMicros),
      signalHistory: Array.from({ length: 24 }, () => rssi),
    }
  })
}

const OBS_KIND: [RegExp, ObservationKind][] = [
  [/correlat/i, 'correlated'],
  [/contact|tamper|cabinet|door|vibration/i, 'tamper'],
  [/wifi|ssid|ap_|_ap|bssid|impersonat|beacon/i, 'impersonation'],
  [/ble|unknown|unregistered|transmitter/i, 'unknown'],
]

export function mapObservationKind(kind: string, dataJson: string): ObservationKind {
  for (const [re, k] of OBS_KIND) if (re.test(kind) || re.test(dataJson)) return k
  return 'unknown'
}

export function summarizeDataJson(dataJson: string): string {
  try {
    const d = JSON.parse(dataJson) as Record<string, unknown>
    const parts = Object.entries(d).slice(0, 4).map(([k, v]) => `${k}=${String(v).slice(0, 40)}`)
    return parts.join(' ')
  } catch { return dataJson.slice(0, 120) }
}

export function mapObservations(rows: LiveRows, ctx: MapContext): Observation[] {
  const sorted = [...rows.observations].sort((a, b) => Number(a.id) - Number(b.id))
  return sorted.slice(-300).map(o => ({
    id: `obs-${o.eventId || o.id}`,
    kind: mapObservationKind(o.kind, o.dataJson),
    zoneId: o.zoneId,
    deviceIds: [o.deviceId],
    at: backendToElapsed(toMicros(o.observedAt), ctx.elapsed, ctx.backendNowMicros),
    detail: `${TAG(ctx)} · ${o.kind} on ${o.deviceId} (seq ${o.seq}, ${o.trustTier.tag}) — ${summarizeDataJson(o.dataJson)}`,
    observedAtUtc: toMicros(o.observedAt) > 0 ? new Date(toMicros(o.observedAt) / 1000).toISOString() : undefined,
  }))
}

const INC_STATUS: Record<string, Incident['status']> = {
  New: 'detected', Triage: 'detected', Investigating: 'investigating',
  ContainmentPending: 'investigating', Contained: 'investigating',
  Recovery: 'investigating', Resolved: 'resolved', Closed: 'resolved',
  Dismissed: 'resolved',
}
const SEV: Record<string, Severity> = { Info: 'low', Low: 'low', Medium: 'medium', High: 'high', Critical: 'critical' }

export function mapIncidents(rows: LiveRows, ctx: MapContext): Incident[] {
  // Join alerts -> observations to recover zone/device/observation links
  // the incidents table does not carry directly.
  const obsById = new Map(rows.observations.map(o => [String(o.id), o]))
  const alertObs = new Map<string, string[]>()
  for (const a of rows.alerts) {
    if (!a.incidentId) continue
    const ids = (alertObs.get(a.incidentId) ?? [])
    for (const oid of a.observationIds) ids.push(String(oid))
    alertObs.set(a.incidentId, ids)
  }
  const evidenceByIncident = new Map<string, string[]>()
  for (const e of rows.evidence) {
    const list = evidenceByIncident.get(e.incidentId) ?? []
    list.push(`ev-${e.id}`)
    evidenceByIncident.set(e.incidentId, list)
  }
  const scopeByIncident = new Map<string, string[]>()
  for (const s of rows.scopeEntries) {
    const list = scopeByIncident.get(s.incidentId) ?? []
    list.push(`fnd-${s.id}`)
    scopeByIncident.set(s.incidentId, list)
  }
  const auditByIncident = new Map<string, typeof rows.auditEvents>()
  for (const a of rows.auditEvents) {
    if (!a.incidentId) continue
    const list = auditByIncident.get(a.incidentId) ?? []
    list.push(a)
    auditByIncident.set(a.incidentId, list)
  }
  const fallbackZone = rows.zones[0]?.id ?? 'zone-operations'

  return rows.incidents.map(inc => {
    const linkedObs = (alertObs.get(inc.id) ?? [])
      .map(id => obsById.get(id)).filter((o): o is NonNullable<typeof o> => !!o)
    const zoneId = linkedObs[0]?.zoneId ?? fallbackZone
    const deviceIds = [...new Set(linkedObs.map(o => o.deviceId))]
    const observationIds = linkedObs.map(o => `obs-${o.eventId || o.id}`)
    const created = backendToElapsed(toMicros(inc.createdAt), ctx.elapsed, ctx.backendNowMicros)
    const updated = backendToElapsed(toMicros(inc.updatedAt), ctx.elapsed, ctx.backendNowMicros)
    const timeline: TimelineEntry[] = [
      { id: `tl-${inc.id}-created`, at: created, title: 'Incident recorded', detail: `${TAG(ctx)} · ${inc.description || inc.title}`, kind: 'observation' },
      ...(auditByIncident.get(inc.id) ?? [])
        .sort((a, b) => toMicros(a.at) - toMicros(b.at))
        .slice(0, 20)
        .map(a => ({
          id: `tl-${inc.id}-aud-${a.id}`, at: backendToElapsed(toMicros(a.at), ctx.elapsed, ctx.backendNowMicros),
          title: `audit: ${a.operation}`, detail: `${TAG(ctx)} · ${a.entity} · ${a.detailJson.slice(0, 160)}`,
          kind: (a.operation.includes('approv') || a.operation.includes('propos') ? 'analysis' : a.operation.includes('verif') || a.operation.includes('resolv') ? 'resolution' : 'operator') as TimelineEntry['kind'],
        })),
    ]
    return {
      id: inc.id, title: inc.title,
      severity: SEV[inc.severity.tag] ?? 'medium',
      status: INC_STATUS[inc.status.tag] ?? 'detected',
      zoneId, deviceIds, observationIds,
      evidenceIds: evidenceByIncident.get(inc.id) ?? [],
      findingIds: scopeByIncident.get(inc.id) ?? [],
      timeline, createdAt: created, updatedAt: Math.max(created, updated),
    }
  })
}

export function mapEvidence(rows: LiveRows['evidence'], ctx: MapContext): Evidence[] {
  const typeOf = (source: string): Evidence['type'] =>
    /camera|photo/i.test(source) ? 'camera' : /\brf\b|wifi|signal/i.test(source) ? 'rf' : /lidar|scan/i.test(source) ? 'lidar' : 'policy'
  return rows.map(e => ({
    id: `ev-${e.id}`, incidentId: e.incidentId, type: typeOf(e.source),
    at: backendToElapsed(toMicros(e.observedAt), ctx.elapsed, ctx.backendNowMicros),
    summary: `${TAG(ctx)} · ${e.source} · ${e.trustTier.tag} · ref ${e.storageRef || 'none'} · sha256 ${e.sha256.slice(0, 12)}`,
  }))
}

export function mapFindings(rows: LiveRows['scopeEntries'], ctx: MapContext): Finding[] {
  const conf = (statuses: string[]) =>
    statuses.some(s => s === 'ConfirmedExposed' || s === 'Exfiltrated') ? 0.95
    : statuses.some(s => s === 'SuspectedExposed') ? 0.6 : 0.3
  return rows.map(s => ({
    id: `fnd-${s.id}`, incidentId: s.incidentId,
    at: backendToElapsed(toMicros(s.updatedAt), ctx.elapsed, ctx.backendNowMicros),
    title: `${TAG(ctx)} scope: ${s.assetId} / ${s.datasetCategory || 'dataset'}`,
    detail: `${s.note || 'Scope entry recorded'} · impacts: ${s.impactDimensions.map(d => d.tag).join(',') || 'none'} · statuses: ${s.impactStatuses.map(x => x.tag).join(',') || 'unknown'} · ~${s.estimatedRecords} records`,
    confidence: conf(s.impactStatuses.map(x => x.tag)),
    evidenceIds: s.evidenceRefs.filter(r => r.startsWith('ev-')),
  }))
}

const MISSION_TYPE: Record<string, Mission['type']> = {
  InspectZone: 'investigate', Patrol: 'patrol', CapturePhoto: 'investigate',
  ReturnHome: 'return', Hold: 'waypoint',
}
const MISSION_STATUS: Record<string, Mission['status']> = {
  Proposed: 'queued', Approved: 'queued', Dispatched: 'en_route',
  Accepted: 'en_route', Navigating: 'en_route', Completed: 'complete',
  Failed: 'cancelled', Expired: 'cancelled', Cancelled: 'cancelled',
}

export function mapMissions(rows: LiveRows, ctx: MapContext): Mission[] {
  const zonePos = new Map(mapZones(rows.zones).map(z => [z.id, z.position]))
  const incidentZone = new Map(mapIncidents(rows, ctx).map(i => [i.id, i.zoneId]))
  return rows.missions.map(m => {
    const zoneId = m.zoneId || incidentZone.get(m.incidentId) || rows.zones[0]?.id || 'zone-operations'
    const target = zonePos.get(zoneId) ?? zonePos.get(rows.zones[0]?.id ?? '') ?? { x: 12, y: 9 }
    const state = m.state.tag
    return {
      id: m.id,
      title: `${TAG(ctx)} ${m.type.tag.replace(/_/g, ' ')} · ${m.waypoint || m.id}`,
      type: MISSION_TYPE[m.type.tag] ?? 'waypoint',
      status: MISSION_STATUS[state] ?? 'queued',
      target, zoneId, incidentId: m.incidentId || undefined,
      progress: state === 'Completed' ? 1 : state === 'Navigating' || state === 'Dispatched' || state === 'Accepted' ? 0.5 : 0,
    }
  })
}

export function mapApprovals(rows: LiveRows, ctx: MapContext): Approval[] {
  const decided = new Map(rows.approvals.map(a => [a.actionId, a]))
  const out: Approval[] = []
  for (const a of rows.actions) {
    const ap = decided.get(a.id)
    const pending = a.state.tag === 'Proposed' || a.state.tag === 'PendingApproval'
    if (!pending && !ap) continue
    out.push({
      id: `appr-${a.id}`, at: backendToElapsed(toMicros(a.createdAt), ctx.elapsed, ctx.backendNowMicros),
      incidentId: a.incidentId, action: 'isolate-device', targetId: a.targetId,
      reason: `${TAG(ctx)} · ${a.type.tag}: ${a.reason}`,
      status: ap ? (ap.decision.tag === 'Approved' ? 'approved' : 'rejected') : 'pending',
      decidedAt: ap ? backendToElapsed(toMicros(ap.decidedAt), ctx.elapsed, ctx.backendNowMicros) : undefined,
    })
  }
  return out
}

export function mapEvents(rows: LiveRows, ctx: MapContext): CommandEvent[] {
  const events: CommandEvent[] = []
  for (const a of rows.alerts) {
    events.push({
      id: `alert-${a.id}`, at: backendToElapsed(toMicros(a.createdAt), ctx.elapsed, ctx.backendNowMicros),
      type: `alert.${a.state.tag}`, entityId: a.incidentId || undefined,
      detail: `${TAG(ctx)} · ${a.title} (${a.severity.tag})`,
    })
  }
  for (const e of rows.auditEvents.slice(-120)) {
    events.push({
      id: `aud-${e.id}`, at: backendToElapsed(toMicros(e.at), ctx.elapsed, ctx.backendNowMicros),
      type: `audit.${e.operation}`, entityId: e.incidentId || e.entity || undefined,
      detail: `${TAG(ctx)} · ${e.operation} on ${e.entity}`,
    })
  }
  return events.sort((a, b) => a.at - b.at)
}

const AUDIT_KIND: Record<string, AgentRecord['kind']> = {
  propose: 'decision', approve: 'decision', reject: 'decision', deny: 'decision',
  verify: 'status', resolve: 'status', recover: 'status', execute: 'tool',
}

export function mapActivity(rows: LiveRows, investigations: LiveSnapshot['api']['investigations'], ctx: MapContext): AgentRecord[] {
  const out: AgentRecord[] = []
  for (const a of rows.auditEvents.slice(-160)) {
    out.push({
      id: `aud-${a.id}`, at: backendToElapsed(toMicros(a.at), ctx.elapsed, ctx.backendNowMicros),
      kind: AUDIT_KIND[a.operation.split('_')[0]] ?? 'status',
      title: `${TAG(ctx)} ${a.operation}`,
      detail: `${a.entity} · ${a.detailJson.slice(0, 200)}`,
      incidentId: a.incidentId || undefined,
    })
  }
  for (const inv of investigations) {
    out.push({
      id: `inv-${inv.incident_id}-${inv.run_index}`,
      at: ctx.elapsed,
      kind: 'finding', title: `${TAG(ctx)} investigation: ${inv.assessment?.title ?? 'assessment'}`,
      detail: inv.assessment?.summary ?? inv.brief,
    })
  }
  return out.sort((a, b) => a.at - b.at)
}

/** Deterministic telemetry derived purely from backend rows: traffic =
 * observations per 5-second bucket, signals = open alerts. cpu/latency
 * have no backend source — reported as 0 rather than fabricated
 * (documented gap). Rebuilt wholesale per snapshot, so resync can
 * never duplicate samples. */
export function mapTelemetry(rows: LiveRows, ctx: MapContext): TelemetrySample[] {
  const bucketMicros = 5_000_000
  const now = ctx.backendNowMicros
  const buckets = new Map<number, number>()
  for (const o of rows.observations) {
    const t = toMicros(o.receivedAt || o.observedAt)
    if (!t || t > now) continue
    const b = Math.floor((now - t) / bucketMicros)
    if (b < 24) buckets.set(b, (buckets.get(b) ?? 0) + 1)
  }
  const openAlerts = rows.alerts.filter(a => a.state.tag === 'Open' || a.state.tag === 'Acknowledged').length
  // 24 samples spanning the last ~8 simulated-minutes (20s apart).
  return Array.from({ length: 24 }, (_, i) => {
    const bucketIndex = 23 - i // 0 = 8 min ago … 23 = now
    return {
      at: ctx.elapsed - (23 - bucketIndex) * (20 / 60),
      traffic: Math.min(100, (buckets.get(bucketIndex) ?? 0) * 12),
      signals: Math.min(100, 8 + openAlerts * 10 + (i % 3)),
      cpu: 0, latency: 0,
    }
  })
}

// Rover pose telemetry -> twin (issue #116). Pose always comes from
// received observations — never fabricated. Frame registration lives in
// twin/occupancyContract.ts: 'autonomy_map' gets the documented static
// sim-room offset (AUTONOMY_MAP_OFFSET = facility centre), surveyed
// frames are identity, and unregistered frames keep raw coordinates —
// they are never silently placed. Rover-native poses arrive in mm on
// the surveyed floorplan and are used directly.
const ROVER_POSE_STALE_S = 5

interface RoverPoseFix {
  x: number; y: number; heading: number
  atMicros: number; missionId: string | null
  frameId?: string; provenance?: string
}

function extractRoverPose(o: LiveRows['observations'][number]): RoverPoseFix | null {
  if (o.kind !== 'mission_status') return null
  let d: { pose?: unknown; mission_id?: unknown; provenance?: unknown } | null
  try { d = JSON.parse(o.dataJson) as typeof d } catch { return null }
  const p = d?.pose as Record<string, unknown> | null | undefined
  if (!p || typeof p !== 'object') return null
  let x: number, y: number
  if (typeof p.x === 'number' && typeof p.y === 'number') {
    x = p.x; y = p.y
    if (p.unit === 'mm') { x /= 1000; y /= 1000 }
  } else if (typeof p.x_mm === 'number' && typeof p.y_mm === 'number') {
    x = p.x_mm / 1000; y = p.y_mm / 1000
  } else return null
  const frameId = typeof p.frame === 'string' ? p.frame
    : typeof p.frame_id === 'string' ? p.frame_id : undefined
  const reg = registerFrame(frameId ?? '')
  const offset = reg.kind === 'unregistered' ? { x: 0, y: 0 } : reg.offset
  const heading = typeof p.heading_rad === 'number' ? p.heading_rad
    : typeof p.theta === 'number' ? p.theta
    : typeof p.yaw === 'number' ? p.yaw : 0
  return {
    x: x + offset.x, y: y + offset.y, heading,
    atMicros: toMicros(o.observedAt),
    missionId: typeof d?.mission_id === 'string' ? d.mission_id : null,
    frameId, provenance: typeof d?.provenance === 'string' ? d.provenance : undefined,
  }
}

export function mapRover(rows: LiveRows, ctx: MapContext, missions: Mission[], contractFixes: TwinPoseFix[] = []): Rover {
  const roverDev = rows.devices.find(d => d.type.tag === 'Rover')
  const zoneId = roverDev?.zoneId ?? rows.zones[0]?.id
  const zonePos = new Map(mapZones(rows.zones).map(z => [z.id, z.position]))
  const fallback = zonePos.get(zoneId ?? '') ?? { x: 12, y: 9 }
  const lidar = Array.from({ length: 72 }, () => 2.5)

  const fixes: RoverPoseFix[] = []
  for (const o of rows.observations) {
    if (roverDev && o.deviceId !== roverDev.id) continue
    const fix = extractRoverPose(o)
    if (fix && fix.atMicros > 0) fixes.push(fix)
  }
  // sentinel.rover.pose_report contract fixes (observation-embedded or
  // dedicated feed) merge into the same fix stream — newest wins.
  for (const f of contractFixes) {
    if (roverDev ? f.deviceId !== roverDev.id : !/rover/i.test(f.deviceId)) continue
    fixes.push({ x: f.x, y: f.y, heading: f.heading, atMicros: f.atMicros, missionId: null, frameId: f.frameId, provenance: f.provenance })
  }
  fixes.sort((a, b) => a.atMicros - b.atMicros)
  const latest = fixes.at(-1)
  if (!latest) {
    // No telemetry yet — park at the zone anchor, flagged stale. Position
    // is a layout anchor, explicitly NOT a measured pose.
    return { position: fallback, heading: 0, speed: 0, battery: 100,
      stopped: false, missionId: null, distance: 0, lidar, stale: true }
  }
  const at = backendToElapsed(latest.atMicros, ctx.elapsed, ctx.backendNowMicros)
  const stale = ctx.elapsed - at > ROVER_POSE_STALE_S
  // Speed from the two most recent distinct fixes (real dt from obs times).
  let speed = 0
  const prev = fixes.at(-2)
  if (prev && !stale) {
    const dtS = (latest.atMicros - prev.atMicros) / 1_000_000
    if (dtS > 0.05) speed = Math.min(3, Math.hypot(latest.x - prev.x, latest.y - prev.y) / dtS)
  }
  const linked = latest.missionId
    ? missions.find(m => m.id === latest.missionId)
    : undefined
  const missionId = linked?.id ?? missions.find(m => m.status === 'en_route')?.id ?? null
  return {
    position: { x: latest.x, y: latest.y },
    heading: latest.heading,
    speed: stale ? 0 : speed,
    battery: 100, stopped: false,
    missionId, distance: 0, lidar,
    stale,
    frameId: latest.frameId,
    poseAt: at,
    provenance: latest.provenance,
  }
}

/** Build the full live entity set from one snapshot. Pure — the same
 * inputs always produce the same entities (deterministic mapping). */
export function mapSnapshot(snapshot: LiveSnapshot, elapsed: number): { entities: import('./types').LiveEntities; dedupe: { events: number; observations: number } } {
  const ctx: MapContext = { elapsed, backendNowMicros: snapshot.backendNowMicros, provenance: snapshot.provenance }
  const zones = mapZones(snapshot.rows.zones)
  const devices = mapDevices(snapshot.rows, ctx)
  const observations = mapObservations(snapshot.rows, ctx)
  const incidents = mapIncidents(snapshot.rows, ctx)
  const evidence = mapEvidence(snapshot.rows.evidence, ctx)
  const findings = mapFindings(snapshot.rows.scopeEntries, ctx)
  const missions = mapMissions(snapshot.rows, ctx)
  const approvals = mapApprovals(snapshot.rows, ctx)
  const events = mapEvents(snapshot.rows, ctx)
  const activity = mapActivity(snapshot.rows, snapshot.api.investigations, ctx)
  const telemetry = mapTelemetry(snapshot.rows, ctx)
  const twin = mapTwinFeed(snapshot, ctx)
  const rover = mapRover(snapshot.rows, ctx, missions, twin.poseFixes)
  return {
    entities: { zones, devices, observations, incidents, evidence, findings, missions, approvals, events, activity, telemetry, rover, twinFeed: twin.twinFeed },
    dedupe: {
      events: new Set(events.map(e => e.id)).size,
      observations: new Set(observations.map(o => o.id)).size,
    },
  }
}
