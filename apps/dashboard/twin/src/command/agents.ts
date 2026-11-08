import type { CommandState, Observation, Point, Severity } from './model'

export type ToolName = 'read_inventory' | 'correlate_observations' | 'dispatch_inspection' | 'collect_evidence' | 'isolate_device'
export type PolicyDecision = { allowed: boolean; requiresApproval: boolean; reason: string }
export interface InvestigationContext { provenance: 'DEMO'; observation: Observation | null; deviceIds: string[]; relatedObservationIds: string[]; activeIncidentIds: string[]; selectedEntityId: string | null }
export interface AgentAssessment { title: string; severity: Severity; confidence: number; summary: string; target: Point; requestIsolation: boolean }
export interface CommandAgentProvider { readonly mode: 'mock' | 'backend'; assess(context: InvestigationContext): AgentAssessment | Promise<AgentAssessment> }
export const TOOL_REGISTRY: Record<ToolName, { label: string; capability: 'read' | 'movement' | 'disruptive'; description: string }> = {
  read_inventory: { label: 'Read device inventory', capability: 'read', description: 'Read the local synthetic device and RF histories.' },
  correlate_observations: { label: 'Correlate observations', capability: 'read', description: 'Match time, location and stable device identifiers.' },
  dispatch_inspection: { label: 'Dispatch bounded inspection', capability: 'movement', description: 'Queue a simulated rover inspection inside the mapped facility.' },
  collect_evidence: { label: 'Collect simulated evidence', capability: 'read', description: 'Produce labelled RF, camera and LiDAR fixture records.' },
  isolate_device: { label: 'Simulate device isolation', capability: 'disruptive', description: 'Record a containment simulation after explicit operator approval.' },
}
export function evaluatePolicy(tool: ToolName, state: CommandState, target?: Point): PolicyDecision {
  const capability = TOOL_REGISTRY[tool].capability
  if (capability === 'disruptive') return { allowed: false, requiresApproval: true, reason: 'Disruptive containment requires a separate operator approval. Execution remains simulated.' }
  if (capability === 'movement' && state.rover.stopped) return { allowed: false, requiresApproval: false, reason: 'Independent emergency stop is latched; movement is inhibited.' }
  if (capability === 'movement' && (!target || !Number.isFinite(target.x) || !Number.isFinite(target.y) || target.x < 0.5 || target.x > 23.5 || target.y < 0.5 || target.y > 17.5)) return { allowed: false, requiresApproval: false, reason: 'Destination is outside the approved demonstration facility.' }
  return { allowed: true, requiresApproval: false, reason: capability === 'read' ? 'Read-only demo analysis is automatically permitted.' : 'Bounded, non-disruptive demo inspection is permitted by patrol policy.' }
}
export function buildAgentContext(state: CommandState, observation: Observation, selectedEntityId: string | null = null): InvestigationContext {
  return { provenance: 'DEMO', observation: structuredClone(observation), deviceIds: [...observation.deviceIds], relatedObservationIds: state.observations.filter(item => item.zoneId === observation.zoneId && Math.abs(item.at - observation.at) <= 15).map(item => item.id), activeIncidentIds: state.incidents.filter(item => item.status !== 'resolved').map(item => item.id), selectedEntityId }
}
export class AgentContextStore {
  private context: InvestigationContext | null = null
  update(state: CommandState, observation: Observation, selectedEntityId: string | null) { this.context = buildAgentContext(state, observation, selectedEntityId); return this.read() }
  select(state: CommandState, selectedEntityId: string | null) {
    const incident = state.incidents.find(item => item.id === selectedEntityId || item.deviceIds.includes(selectedEntityId ?? ''))
    const zone = state.zones.find(item => item.id === selectedEntityId)
    const deviceIds = incident?.deviceIds ?? state.devices.filter(item => item.id === selectedEntityId || item.zoneId === zone?.id).map(item => item.id)
    const observations = state.observations.filter(item => item.deviceIds.some(id => deviceIds.includes(id)))
    this.context = { provenance: 'DEMO', observation: observations.at(-1) ?? null, deviceIds, relatedObservationIds: observations.map(item => item.id), activeIncidentIds: state.incidents.filter(item => item.status !== 'resolved').map(item => item.id), selectedEntityId }
  }
  read() { return this.context ? structuredClone(this.context) : null }
  clear() { this.context = null }
}
export class MockAgentProvider implements CommandAgentProvider {
  readonly mode = 'mock' as const
  assess(context: InvestigationContext): AgentAssessment {
    if (context.provenance !== 'DEMO') throw new Error('The mock provider accepts DEMO context only.')
    if (!context.observation) throw new Error('An observation is required before assessment.')
    const kind = context.observation.kind
    if (kind === 'impersonation') return { title: 'Access point identity mismatch', severity: 'high', confidence: 0.94, summary: 'An advertised PHANTOM-NET SSID has a fingerprint absent from the synthetic AP allowlist. Physical verification is required.', target: { x: 20, y: 13 }, requestIsolation: true }
    if (kind === 'tamper') return { title: 'Cabinet access anomaly', severity: 'high', confidence: 0.87, summary: 'A cabinet contact and vibration signature changed outside the baseline. A simulated visual inspection can distinguish maintenance from tampering.', target: { x: 1.5, y: 11 }, requestIsolation: false }
    if (kind === 'correlated') return { title: 'Correlated RF and cabinet anomaly', severity: 'critical', confidence: 0.96, summary: 'A new BLE signature and cabinet contact event share a 3-second window and the same server aisle. Correlation does not establish malicious intent.', target: { x: 1.5, y: 11 }, requestIsolation: false }
    return { title: 'Unregistered transmitter detected', severity: 'medium', confidence: 0.89, summary: 'A BLE transmitter is absent from the asset baseline. Signal location overlaps the server aisle; visual evidence is needed before a conclusion.', target: { x: 1.5, y: 15 }, requestIsolation: false }
  }
}
/** An injected inference client can later provide structured proposals. It has no actuator API. */
export interface NemotronTransport { infer(context: Readonly<InvestigationContext>, signal?: AbortSignal): Promise<AgentAssessment> }
export class NemotronAgentProvider implements CommandAgentProvider {
  readonly mode = 'backend' as const
  constructor(private transport: NemotronTransport) {}
  async assess(context: InvestigationContext): Promise<AgentAssessment> {
    const result = await this.transport.infer(structuredClone(context))
    if (!result.title || !Number.isFinite(result.confidence) || result.confidence < 0 || result.confidence > 1 || !Number.isFinite(result.target?.x) || !Number.isFinite(result.target?.y) || !['low', 'medium', 'high', 'critical'].includes(result.severity) || typeof result.summary !== 'string' || typeof result.requestIsolation !== 'boolean') throw new Error('Invalid structured Nemotron assessment')
    return result
  }
}
