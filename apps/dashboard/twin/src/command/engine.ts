import { MockAgentProvider, buildAgentContext, evaluatePolicy } from './agents'
import { HOME, createInitialState } from './fixtures'
import type { AgentRecord, CommandState, Incident, Mission, ObservationKind, Point, Severity, TimelineEntry } from './model'

const FIXED_STEP = 0.25
const provider = new MockAgentProvider()
const copy = (state: CommandState) => structuredClone(state)
const round = (n: number) => Math.round(n * 1000000) / 1000000
function id(state: CommandState, prefix: string) { return `${prefix}-${String(state.sequence++).padStart(4, '0')}` }
function emit(state: CommandState, type: string, detail: string, entityId?: string) { state.events.push({ id: id(state, 'event'), at: state.elapsed, type, entityId, detail }); state.events = state.events.slice(-400) }
function record(state: CommandState, kind: AgentRecord['kind'], title: string, detail: string, incidentId?: string, tool?: string, outcome?: string) { state.activity.push({ id: id(state, 'agent'), at: state.elapsed, kind, title, detail, incidentId, tool, outcome }); state.activity = state.activity.slice(-240) }
function timeline(state: CommandState, incident: Incident, kind: TimelineEntry['kind'], title: string, detail: string) { incident.timeline.push({ id: id(state, 'timeline'), at: state.elapsed, kind, title, detail }); incident.updatedAt = state.elapsed }
function zoneFor(point: Point) { return point.x < 14 ? 'zone-server' : point.y >= 9 ? 'zone-network' : 'zone-operations' }
export function isNavigable(point: Point): boolean {
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || point.x < 0.5 || point.x > 23.5 || point.y < 0.5 || point.y > 17.5) return false
  if (Math.abs(point.x - 14) < 0.5 && Math.abs(point.y - 4.5) > 1 && Math.abs(point.y - 13.5) > 1) return false
  if (point.x > 14 && Math.abs(point.y - 9) < 0.5 && Math.abs(point.x - 18) > 1) return false
  for (const x of [3, 7, 11]) for (const y of [3, 7, 11, 15]) if (Math.abs(point.x - x) < 1.1 && Math.abs(point.y - y) < 1.2) return false
  return true
}
function nearestNode(point: Point): Point {
  let best: Point = { ...HOME }; let distance = Infinity
  for (let x = 0.5; x <= 23.5; x += 0.5) for (let y = 0.5; y <= 17.5; y += 0.5) {
    const candidate = { x, y }; const d = Math.hypot(x - point.x, y - point.y)
    if (isNavigable(candidate) && d < distance) { distance = d; best = candidate }
  }
  return best
}
/** A deterministic grid route avoids racks and uses the facility's three doorways. */
export function planRoute(start: Point, target: Point): Point[] {
  const from = nearestNode(start); const to = nearestNode(target)
  const key = (p: Point) => `${p.x},${p.y}`
  const queue = [from]; const previous = new Map<string, Point | null>([[key(from), null]])
  for (let cursor = 0; cursor < queue.length; cursor++) {
    const current = queue[cursor]
    if (key(current) === key(to)) break
    for (const [dx, dy] of [[0.5, 0], [0, 0.5], [-0.5, 0], [0, -0.5]]) {
      const next = { x: current.x + dx, y: current.y + dy }
      if (isNavigable(next) && !previous.has(key(next))) { previous.set(key(next), current); queue.push(next) }
    }
  }
  if (!previous.has(key(to))) return [{ ...start }]
  const route: Point[] = []; let cursor: Point | null = to
  while (cursor) { route.unshift(cursor); cursor = previous.get(key(cursor)) ?? null }
  // Keep corners only to make both Three paths and the mission record compact.
  const simplified = route.filter((point, index) => index === 0 || index === route.length - 1 || (point.x - route[index - 1].x !== route[index + 1].x - point.x) || (point.y - route[index - 1].y !== route[index + 1].y - point.y))
  if (Math.hypot(start.x - from.x, start.y - from.y) > 0.001) simplified.unshift({ ...start })
  return simplified
}
function queueMission(state: CommandState, type: Mission['type'], title: string, target: Point, incidentId?: string, zoneId?: string) {
  const mission: Mission = { id: id(state, 'mission'), type, title, target: nearestNode(target), zoneId: zoneId ?? zoneFor(target), incidentId, status: 'queued', progress: 0 }
  state.missions.push(mission); emit(state, 'mission.queued', title, mission.id)
  return mission
}
function injectMutable(state: CommandState, kind: ObservationKind) {
  const zoneId = kind === 'impersonation' ? 'zone-network' : 'zone-server'
  const deviceIds = kind === 'impersonation' ? ['wifi-08', 'ap-03'] : kind === 'tamper' ? ['sensor-01', 'rack-07'] : kind === 'correlated' ? ['ble-04', 'sensor-01', 'rack-07'] : ['ble-04']
  const detail = kind === 'impersonation' ? 'DEMO RF monitor observed PHANTOM-NET with a mismatched BSSID and vendor fingerprint.' : kind === 'tamper' ? 'DEMO cabinet contact opened at SRV-07; a short vibration burst preceded the change.' : kind === 'correlated' ? 'DEMO BLE signature and cabinet contact transitions overlap in the west server aisle.' : 'DEMO passive monitor observed an unregistered BLE advertisement at −48 dBm near the west server aisle.'
  const observation = { id: id(state, 'observation'), kind, zoneId, deviceIds, at: state.elapsed, detail }
  state.observations.push(observation)
  state.devices = state.devices.map(device => deviceIds.includes(device.id) ? { ...device, status: kind === 'correlated' || kind === 'impersonation' ? 'threat' : 'watch', risk: kind === 'correlated' ? 94 : kind === 'impersonation' ? 87 : kind === 'tamper' ? 76 : 58, lastSeen: state.elapsed, ...(device.id === 'ble-04' ? { name: 'UNREGISTERED-BLE', vendor: 'Unregistered signature', rssi: -48 } : {}) } : device)
  record(state, 'observation', kind === 'impersonation' ? 'Identity mismatch observed' : kind === 'tamper' ? 'Cabinet event observed' : kind === 'correlated' ? 'Multiple observations linked' : 'Unknown transmitter observed', detail)
  emit(state, 'observation.received', detail, observation.id)
}
export function injectObservation(state: CommandState, kind: ObservationKind): CommandState {
  if (!['unknown', 'impersonation', 'tamper', 'correlated'].includes(kind)) return state
  const next = copy(state); injectMutable(next, kind); return next
}
function correlate(state: CommandState) {
  for (const observation of state.observations) {
    if (state.elapsed - observation.at < 1.25 || state.incidents.some(incident => incident.observationIds.includes(observation.id))) continue
    const assessment = provider.assess(buildAgentContext(state, observation))
    const related = state.incidents.find(incident => incident.status !== 'resolved' && incident.zoneId === observation.zoneId && Math.abs(incident.createdAt - observation.at) <= 12)
    if (related) {
      related.observationIds.push(observation.id); related.deviceIds = [...new Set([...related.deviceIds, ...observation.deviceIds])]
      if (observation.kind === 'tamper' || observation.kind === 'correlated') { related.title = 'Correlated RF and cabinet anomaly'; related.severity = 'critical' }
      timeline(state, related, 'analysis', 'Related observation correlated', observation.detail)
      record(state, 'correlation', 'Additional signal correlated', 'Device location and observation window match the open investigation.', related.id, 'correlate_observations', 'matched')
      continue
    }
    const incident: Incident = { id: id(state, 'incident'), title: assessment.title, severity: assessment.severity, status: 'detected', zoneId: observation.zoneId, deviceIds: [...observation.deviceIds], observationIds: [observation.id], evidenceIds: [], findingIds: [], timeline: [], createdAt: state.elapsed, updatedAt: state.elapsed }
    state.incidents.push(incident)
    timeline(state, incident, 'observation', 'Observation received', observation.detail)
    record(state, 'tool', 'Inventory baseline queried', `Read ${state.devices.length} synthetic identities; compare time, zone and fingerprint.`, incident.id, 'read_inventory', 'complete')
    record(state, 'correlation', 'Location and identity correlated', assessment.summary, incident.id, 'correlate_observations', 'anomaly')
    const evidence = { id: id(state, 'evidence'), incidentId: incident.id, type: 'rf' as const, at: state.elapsed, summary: observation.detail }
    state.evidence.push(evidence); incident.evidenceIds.push(evidence.id)
    const finding = { id: id(state, 'finding'), incidentId: incident.id, at: state.elapsed, title: 'Initial assessment requires physical context', detail: assessment.summary, confidence: assessment.confidence, evidenceIds: [evidence.id] }
    state.findings.push(finding); incident.findingIds.push(finding.id)
    timeline(state, incident, 'analysis', 'Automatic incident created', assessment.summary)
    record(state, 'decision', 'Incident opened automatically', `${assessment.severity.toUpperCase()} · ${assessment.title}. Requesting a policy check for non-disruptive inspection.`, incident.id)
    emit(state, 'incident.created', incident.title, incident.id)
  }
  for (const incident of state.incidents) {
    if (incident.status !== 'detected' || state.elapsed - incident.createdAt < 1.5) continue
    const observation = state.observations.find(item => incident.observationIds.includes(item.id))
    const assessment = observation ? provider.assess(buildAgentContext(state, observation)) : { target: { x: incident.zoneId === 'zone-server' ? 1.5 : 18, y: incident.zoneId === 'zone-network' ? 13.5 : 4.5 } }
    const policy = evaluatePolicy('dispatch_inspection', state, assessment.target)
    if (!policy.allowed) continue
    const mission = queueMission(state, 'investigate', `Inspect ${incident.title.toLowerCase()}`, assessment.target, incident.id, incident.zoneId)
    incident.status = 'investigating'
    const evidence = { id: id(state, 'evidence'), incidentId: incident.id, type: 'policy' as const, at: state.elapsed, summary: `DEMO policy P-INSPECT-01: ${policy.reason}` }
    state.evidence.push(evidence); incident.evidenceIds.push(evidence.id)
    timeline(state, incident, 'mission', 'Inspection authorized by policy', `R-01 assigned mission ${mission.id}. ${policy.reason}`)
    record(state, 'tool', 'Bounded inspection authorized', policy.reason, incident.id, 'dispatch_inspection', 'policy allowed')
    record(state, 'decision', 'Rover investigation queued', 'Navigate the mapped corridors; collect synthetic RF, visual and LiDAR evidence at the target.', incident.id)
    emit(state, 'investigation.started', 'Autonomous bounded inspection started', incident.id)
  }
}
function finishCollection(state: CommandState, mission: Mission) {
  const incident = state.incidents.find(item => item.id === mission.incidentId)
  if (incident) {
    const impersonation = incident.observationIds.some(obsId => state.observations.find(observation => observation.id === obsId)?.kind === 'impersonation')
    const records = [
      { type: 'camera' as const, summary: impersonation ? 'DEMO camera fixture: unregistered test AP is visible on network workbench B-04.' : 'DEMO camera fixture: labelled service beacon and maintenance technician marker match the scheduled work order.' },
      { type: 'lidar' as const, summary: 'DEMO LiDAR fixture: corridor remains clear; no unexpected occupancy or obstruction.' },
      { type: 'rf' as const, summary: impersonation ? 'DEMO RF fixture: duplicate PHANTOM-NET SSID persists with an unapproved fingerprint.' : 'DEMO RF fixture: short-range signal localizes to the labelled service device; no traffic contents or exfiltration are inferred.' },
    ].map(item => ({ ...item, id: id(state, 'evidence'), incidentId: incident.id, at: state.elapsed }))
    state.evidence.push(...records); incident.evidenceIds.push(...records.map(item => item.id))
    timeline(state, incident, 'evidence', 'Rover evidence attached', 'Synthetic camera, LiDAR and RF records added to the investigation.')
    record(state, 'tool', 'Evidence collection complete', 'Three fixture records attached with traceable IDs; the agent will reconcile them with the baseline.', incident.id, 'collect_evidence', 'complete')
    const finding = { id: id(state, 'finding'), incidentId: incident.id, at: state.elapsed, title: impersonation ? 'Unapproved AP identity confirmed in simulation' : 'Authorized maintenance explains the anomaly', detail: impersonation ? 'Physical and RF fixture records agree on an unapproved access point. A simulated isolation action awaits explicit operator approval.' : 'The fixture work order and visible service label explain the observed signature. The mock investigation is resolved; RF metadata alone did not establish malicious intent.', confidence: impersonation ? 0.97 : 0.98, evidenceIds: [...records.map(item => item.id), ...incident.evidenceIds.filter(eid => state.evidence.find(item => item.id === eid)?.type === 'policy')] }
    state.findings.push(finding); incident.findingIds.push(finding.id)
    record(state, 'finding', finding.title, finding.detail, incident.id)
    emit(state, 'finding.created', finding.title, finding.id)
    if (impersonation) {
      const policy = evaluatePolicy('isolate_device', state)
      state.approvals.push({ id: id(state, 'approval'), at: state.elapsed, incidentId: incident.id, action: 'isolate-device', targetId: 'wifi-08', reason: policy.reason, status: 'pending' })
      incident.status = 'investigating'
      timeline(state, incident, 'analysis', 'Operator decision required', 'Simulated containment is proposed. No isolation has occurred.')
      record(state, 'decision', 'Containment held for operator approval', policy.reason, incident.id, 'isolate_device', 'approval required')
      emit(state, 'approval.requested', 'Simulated device isolation requires an operator decision', incident.id)
    } else resolveIncident(state, incident, 'Maintenance context verified', 'All simulated observations are explained by the authorized service fixture. Investigation closed automatically.')
  }
  mission.status = 'complete'; mission.progress = 1; state.rover.missionId = null; state.rover.speed = 0
  emit(state, 'mission.complete', mission.title, mission.id)
}
function resolveIncident(state: CommandState, incident: Incident, title: string, detail: string) {
  incident.status = 'resolved'; timeline(state, incident, 'resolution', title, detail)
  record(state, 'status', 'Investigation resolved', detail, incident.id)
  for (const device of state.devices) if (incident.deviceIds.includes(device.id) && !state.incidents.some(other => other.id !== incident.id && other.status !== 'resolved' && other.deviceIds.includes(device.id))) {
    device.status = 'healthy'; device.risk = 6
    if (device.id === 'ble-04') { device.name = 'SERVICE-TAG-04'; device.vendor = 'Authorized maintenance fixture' }
  }
  emit(state, 'incident.resolved', title, incident.id)
}
function moveRover(state: CommandState) {
  if (state.rover.stopped) { state.rover.speed = 0; return }
  let mission = state.missions.find(item => item.id === state.rover.missionId)
  if (!mission || mission.status === 'cancelled' || mission.status === 'complete') {
    mission = state.missions.find(item => item.status === 'queued')
    if (!mission) { state.rover.speed = 0; state.rover.missionId = null; return }
    mission.route = planRoute(state.rover.position, mission.target); mission.routeIndex = 1; mission.travelled = 0
    mission.routeLength = mission.route.reduce((sum, point, index, points) => sum + (index ? Math.hypot(point.x - points[index - 1].x, point.y - points[index - 1].y) : 0), 0)
    mission.status = 'en_route'; state.rover.missionId = mission.id
    record(state, 'status', 'R-01 navigating to target', `${mission.title} · ${(mission.routeLength ?? 0).toFixed(1)} m along mapped corridors.`, mission.incidentId)
    emit(state, 'mission.started', mission.title, mission.id)
  }
  if (mission.status === 'collecting') {
    state.rover.speed = 0
    // Capture requires active rover time; the facility clock continues during E-stop.
    mission.collectionElapsed = round((mission.collectionElapsed ?? 0) + FIXED_STEP)
    if (mission.collectionElapsed >= 4) finishCollection(state, mission)
    return
  }
  let remaining = 1.7 * FIXED_STEP
  const route = mission.route ?? []
  state.rover.speed = 1.7
  while (remaining > 0 && (mission.routeIndex ?? 1) < route.length) {
    const next = route[mission.routeIndex ?? 1]; const p = state.rover.position
    const distance = Math.hypot(next.x - p.x, next.y - p.y)
    const step = Math.min(distance, remaining)
    if (distance > 0.00001) {
      state.rover.heading = Math.atan2(next.y - p.y, next.x - p.x)
      state.rover.position = { x: round(p.x + (next.x - p.x) / distance * step), y: round(p.y + (next.y - p.y) / distance * step) }
      state.rover.distance = round(state.rover.distance + step); mission.travelled = round((mission.travelled ?? 0) + step)
    }
    remaining -= step
    if (distance <= step + 0.00001) { state.rover.position = { ...next }; mission.routeIndex = (mission.routeIndex ?? 1) + 1 }
  }
  mission.progress = Math.min(0.95, (mission.travelled ?? 0) / Math.max(mission.routeLength ?? 1, 0.01) * 0.95)
  if ((mission.routeIndex ?? 1) >= route.length) {
    state.rover.speed = 0
    if (mission.type === 'investigate') {
      mission.status = 'collecting'; mission.collectingAt = state.elapsed; mission.collectionElapsed = 0
      const incident = state.incidents.find(item => item.id === mission.incidentId)
      if (incident) { incident.status = 'collecting'; timeline(state, incident, 'evidence', 'Rover reached inspection point', 'Collecting synthetic camera, RF and LiDAR evidence.'); record(state, 'status', 'Inspection in progress', 'R-01 is stationary at the mapped inspection point.', incident.id) }
      emit(state, 'mission.collecting', 'Synthetic evidence capture started', mission.id)
    } else { mission.status = 'complete'; mission.progress = 1; state.rover.missionId = null; emit(state, 'mission.complete', mission.title, mission.id) }
  }
}
function scenarioStep(state: CommandState) {
  if (state.scenario === 'patrol') {
    if (!state.missions.some(item => item.status === 'queued' || item.status === 'en_route' || item.status === 'collecting')) {
      const waypoints = [{ x: 1.5, y: 1.5 }, { x: 1.5, y: 16.5 }, { x: 20, y: 13.5 }, HOME]
      queueMission(state, 'patrol', `Routine patrol · checkpoint ${state.scenarioStep % 4 + 1}`, waypoints[state.scenarioStep % 4]); state.scenarioStep++
    }
  } else if (state.scenarioStep === 0 && state.elapsed >= 3) { injectMutable(state, state.scenario === 'resolution' || state.scenario === 'correlated' ? 'unknown' : state.scenario); state.scenarioStep = 1 }
  else if (state.scenario === 'correlated' && state.scenarioStep === 1 && state.elapsed >= 4.5) { injectMutable(state, 'tamper'); state.scenarioStep = 2 }
}
function sampleTelemetry(state: CommandState) {
  const t = state.elapsed; const active = state.incidents.filter(item => item.status !== 'resolved').length
  state.telemetry.push({ at: t, traffic: Math.round(41 + Math.sin(t * 0.41) * 10 + active * 9), signals: 32 + active, cpu: Math.round(23 + Math.sin(t * 0.29) * 4 + active * 7), latency: Math.round(12 + Math.cos(t * 0.31) * 3 + active * 2) }); state.telemetry = state.telemetry.slice(-60)
  state.devices = state.devices.map((device, i) => {
    const rssi = Math.round((device.kind === 'ble' ? -59 : -42) + Math.sin((t + i) * 0.7) * 4 + (device.status !== 'healthy' ? 10 : 0))
    return { ...device, rssi, signalHistory: [...device.signalHistory.slice(-23), rssi], lastSeen: t, ...(device.kind === 'rover' ? { position: { ...state.rover.position }, zoneId: zoneFor(state.rover.position) } : {}) }
  })
  state.rover.lidar = state.rover.lidar.map((_, i) => round(2.6 + Math.sin(i * 0.53 + state.rover.position.x * 0.05) * 0.8 + Math.cos(i * 0.19 + state.rover.position.y * 0.1) * 0.6))
}
export function advanceSimulation(state: CommandState, seconds: number): CommandState {
  if (state.simulation !== 'running' || !Number.isFinite(seconds) || seconds <= 0) return state
  const next = copy(state); const duration = (next.tickRemainder ?? 0) + Math.min(seconds, 300) * next.speed
  const steps = Math.floor((duration + 1e-9) / FIXED_STEP); next.tickRemainder = round(duration - steps * FIXED_STEP)
  for (let i = 0; i < steps; i++) {
    next.elapsed = round(next.elapsed + FIXED_STEP); scenarioStep(next); correlate(next); moveRover(next)
    next.rover.battery = round(Math.max(5, next.rover.battery - (next.rover.speed ? 0.0015 : 0.00025)))
    if (Number.isInteger(next.elapsed)) sampleTelemetry(next)
  }
  return next
}
export function changeSimulation(state: CommandState, action: 'start' | 'pause'): CommandState {
  if (action === 'pause' && state.simulation !== 'running' || action === 'start' && state.simulation === 'running') return state
  const next = copy(state); next.simulation = action === 'start' ? 'running' : 'paused'
  emit(next, action === 'start' ? 'simulation.started' : 'simulation.paused', action === 'start' ? 'Deterministic demo clock running' : 'Demo clock paused; all movement and analysis frozen')
  return next
}
export function setEmergencyStop(state: CommandState, stopped: boolean): CommandState {
  if (state.rover.stopped === stopped) return state
  const next = copy(state); next.rover.stopped = stopped; next.rover.speed = 0
  emit(next, stopped ? 'rover.emergency_stop' : 'rover.stop_released', stopped ? 'Independent emergency stop latched; simulated movement and evidence capture inhibited' : 'Operator released the emergency stop; the existing mission queue and simulation controls still apply', 'rover-01')
  record(next, 'status', stopped ? 'Emergency stop latched' : 'Emergency stop released', stopped ? 'Movement and evidence capture are inhibited independently of the simulation clock and agent.' : 'Existing route, capture progress and queue preserved. Paused simulations remain paused.')
  return next
}
export function requestWaypoint(state: CommandState, target: Point, zoneId?: string): CommandState {
  const next = copy(state); const policy = evaluatePolicy('dispatch_inspection', state, target)
  if (!policy.allowed) { emit(next, 'mission.rejected', policy.reason, 'rover-01'); return next }
  const boundedTarget = nearestNode(target)
  queueMission(next, 'waypoint', 'Operator waypoint inspection', boundedTarget, undefined, zoneId ?? zoneFor(boundedTarget))
  record(next, 'decision', 'Operator waypoint queued', `DEMO destination (${boundedTarget.x.toFixed(1)}, ${boundedTarget.y.toFixed(1)}) m; a navigable inspection point is used.`)
  return next
}
export function requestReturnHome(state: CommandState): CommandState {
  const next = copy(state)
  for (const mission of next.missions) if (!['complete', 'cancelled'].includes(mission.status)) { mission.status = 'cancelled'; const incident = next.incidents.find(item => item.id === mission.incidentId); if (incident) { incident.status = 'investigating'; timeline(next, incident, 'operator', 'Inspection interrupted by operator', 'Return-to-home takes precedence. Evidence remains preserved; no resolution is inferred.') } }
  next.rover.missionId = null; next.rover.speed = 0
  queueMission(next, 'return', 'Return to home station', HOME, undefined, 'zone-operations')
  record(next, 'decision', 'Return to home requested', next.rover.stopped ? 'Mission queued; emergency stop remains latched until explicitly released.' : 'Previous movement tasks cancelled; return route will run with the demo clock.')
  return next
}
export function decideApproval(state: CommandState, approvalId: string, approve: boolean): CommandState {
  const original = state.approvals.find(item => item.id === approvalId)
  if (!original || original.status !== 'pending') return state
  const next = copy(state); const approval = next.approvals.find(item => item.id === approvalId)!
  approval.status = approve ? 'approved' : 'rejected'; approval.decidedAt = next.elapsed
  const incident = next.incidents.find(item => item.id === approval.incidentId)
  if (incident) {
    timeline(next, incident, 'operator', approve ? 'Operator approved simulated containment' : 'Operator rejected containment', approve ? 'A demo isolation record was created. No network or hardware action was sent.' : 'No containment action was performed. The incident remains open for operator review.')
    record(next, 'decision', approve ? 'Simulated containment approved' : 'Containment proposal rejected', 'Explicit demo operator decision recorded.', incident.id, 'isolate_device', approval.status)
    if (approve) { emit(next, 'action.simulated', 'DEMO ONLY: isolation recorded without contacting any service', approval.targetId); resolveIncident(next, incident, 'Simulated containment verified', 'Operator-approved containment was recorded in the demo. No real device was isolated.') }
  }
  emit(next, 'approval.decided', `Operator ${approval.status} the simulated action`, approval.id)
  return next
}
export function retryInspection(state: CommandState, incidentId: string): CommandState {
  const incident = state.incidents.find(item => item.id === incidentId)
  if (!incident || incident.status === 'resolved' || state.approvals.some(item => item.incidentId === incidentId && item.status === 'pending') || state.missions.some(item => item.incidentId === incidentId && ['queued', 'en_route', 'collecting'].includes(item.status))) return state
  const next = copy(state); const target = next.incidents.find(item => item.id === incidentId)!
  target.status = 'detected'
  timeline(next, target, 'operator', 'Inspection reassigned by operator', 'A fresh policy check is required. An emergency stop continues to inhibit dispatch.')
  emit(next, 'inspection.reassigned', 'Operator requested another bounded inspection', incidentId)
  return next
}
export function createOperatorIncident(state: CommandState, title: string, zoneId: string, severity: Severity): CommandState {
  if (!title.trim() || !state.zones.some(zone => zone.id === zoneId) || !['low', 'medium', 'high', 'critical'].includes(severity)) return state
  const next = copy(state)
  const incident: Incident = { id: id(next, 'incident'), title: title.trim().slice(0, 160), severity, status: 'detected', zoneId, deviceIds: [], observationIds: [], evidenceIds: [], findingIds: [], timeline: [], createdAt: next.elapsed, updatedAt: next.elapsed }
  next.incidents.push(incident); timeline(next, incident, 'operator', 'Operator incident created', 'A demo operator report triggered the standard policy-controlled inspection workflow.')
  record(next, 'decision', 'Operator report received', incident.title, incident.id); emit(next, 'incident.created', incident.title, incident.id)
  return next
}
export { createInitialState }
