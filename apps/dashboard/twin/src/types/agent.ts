export type AgentStatus = 'idle' | 'investigating' | 'awaiting_approval' | 'complete' | 'failed' | 'cancelled'

export interface AgentContext {
  incidentId: string
  deviceIds: string[]
  evidenceIds: string[]
  provenance: 'SYNTHETIC' | 'REPLAY' | 'LIVE'
}

export interface AgentTask {
  id: string
  title: string
  context: AgentContext
}

export interface AgentFinding {
  id: string
  taskId: string
  summary: string
  confidence: number
  evidenceIds: string[]
  uncertainty: string
}

export interface AgentAction {
  id: string
  taskId: string
  kind: 'request_inspection' | 'propose_containment' | 'annotate_incident'
  targetId: string
  description: string
  requiresApproval: true
}

export interface ActionApproval {
  id: string
  action: AgentAction
  requestedBy: string
  status: 'pending' | 'approved' | 'rejected'
  decidedBy?: string
  reason?: string
}

interface EventBase { id: string; taskId: string; at: string; provenance: AgentContext['provenance'] }
export type AgentEvent = EventBase & (
  | { type: 'status'; status: AgentStatus }
  | { type: 'finding'; finding: AgentFinding }
  | { type: 'approval'; approval: ActionApproval }
  | { type: 'action'; action: AgentAction; outcome: 'simulated' }
)

/** A backend adapter must enforce identity, authorization and approval server-side. */
export interface AgentProvider {
  readonly mode: 'mock' | 'backend'
  subscribe(listener: (event: AgentEvent) => void): () => void
  investigate(task: AgentTask, signal?: AbortSignal): Promise<void>
  decide(approvalId: string, decision: 'approved' | 'rejected', actorId: string, reason: string): Promise<void>
  dispose(): void
}
