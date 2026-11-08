import type { ActionApproval, AgentEvent, AgentProvider, AgentTask } from '@/types/agent'
import { FIXTURE_TIME } from '@/mock/security'

/** Deterministic event stream; never contacts a model, network, or actuator. */
export class MockAgentProvider implements AgentProvider {
  readonly mode = 'mock' as const
  private listeners = new Set<(event: AgentEvent) => void>()
  private approvals = new Map<string, ActionApproval>()
  private contexts = new Map<string, AgentTask['context']>()
  private sequence = 0
  private disposed = false

  subscribe(listener: (event: AgentEvent) => void) {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  private emit(taskId: string, payload: AgentEvent extends infer E ? E extends AgentEvent ? Omit<E, 'id' | 'taskId' | 'at' | 'provenance'> : never : never) {
    if (this.disposed) return
    const event = {
      id: `mock-event-${++this.sequence}`, taskId,
      at: new Date(Date.parse(FIXTURE_TIME) + this.sequence * 1000).toISOString(),
      provenance: this.contexts.get(taskId)?.provenance ?? 'SYNTHETIC', ...payload,
    } as AgentEvent
    this.listeners.forEach(listener => listener(event))
  }

  async investigate(task: AgentTask, signal?: AbortSignal) {
    if (this.disposed) throw new Error('Provider has been disposed')
    if (task.context.provenance !== 'SYNTHETIC') throw new Error('Mock provider accepts synthetic context only')
    if (this.contexts.has(task.id)) throw new Error('Task IDs must be unique')
    this.contexts.set(task.id, task.context)
    this.emit(task.id, { type: 'status', status: 'investigating' })
    await Promise.resolve()
    if (this.disposed || signal?.aborted) {
      this.emit(task.id, { type: 'status', status: 'cancelled' })
      return
    }
    this.emit(task.id, { type: 'finding', finding: {
      id: `finding-${task.id}`, taskId: task.id,
      summary: 'Fixture cabinet contact and unknown access point share a zone.',
      confidence: 0.72, evidenceIds: [...task.context.evidenceIds],
      uncertainty: 'Synthetic correlation only. Data exposure and exfiltration remain unverified.',
    } })
    const approval: ActionApproval = {
      id: `approval-${task.id}`, requestedBy: 'mock-nemotron', status: 'pending',
      action: { id: `action-${task.id}`, taskId: task.id, kind: 'request_inspection', targetId: 'rover-01',
        description: 'Simulate a bounded inspection proposal for Lab A.', requiresApproval: true },
    }
    this.approvals.set(approval.id, approval)
    this.emit(task.id, { type: 'approval', approval })
    this.emit(task.id, { type: 'status', status: 'awaiting_approval' })
  }

  async decide(approvalId: string, decision: 'approved' | 'rejected', actorId: string, reason: string) {
    if (this.disposed) throw new Error('Provider has been disposed')
    const pending = this.approvals.get(approvalId)
    if (!pending || pending.status !== 'pending') throw new Error('Approval is not pending')
    if (!actorId.trim() || actorId === pending.requestedBy || !reason.trim()) throw new Error('An independent actor and reason are required')
    const approval = { ...pending, status: decision, decidedBy: actorId, reason }
    this.approvals.set(approvalId, approval)
    this.emit(approval.action.taskId, { type: 'approval', approval })
    if (decision === 'approved') this.emit(approval.action.taskId, { type: 'action', action: approval.action, outcome: 'simulated' })
    this.emit(approval.action.taskId, { type: 'status', status: 'complete' })
  }

  dispose() { this.disposed = true; this.listeners.clear(); this.approvals.clear(); this.contexts.clear() }
}
