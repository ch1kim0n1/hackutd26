import { beforeEach, describe, expect, it } from 'vitest'
import { MockAgentProvider } from '../src/lib/agents/mock-provider'
import { agentContext } from '../src/mock/security'
import { usePhantomStore } from '../src/store/use-phantom-store'
import type { AgentEvent } from '../src/types/agent'

const task = { id: 'test-task', title: 'Fixture investigation', context: agentContext }
describe('deterministic agent boundary', () => {
  beforeEach(() => usePhantomStore.getState().resetAgent())
  it('streams repeatable findings and waits for a human decision before a simulated action', async () => {
    const provider = new MockAgentProvider()
    const events: AgentEvent[] = []
    provider.subscribe(event => { events.push(event); usePhantomStore.getState().receive(event) })
    await provider.investigate(task)
    expect(events.map(event => event.type)).toEqual(['status', 'finding', 'approval', 'status'])
    expect(events.some(event => event.type === 'action')).toBe(false)
    expect(usePhantomStore.getState().status).toBe('awaiting_approval')
    const approval = usePhantomStore.getState().approvals[0]
    await expect(provider.decide(approval.id, 'approved', 'mock-nemotron', 'self approval')).rejects.toThrow()
    await provider.decide(approval.id, 'approved', 'demo-operator', 'Reviewed')
    expect(events.filter(event => event.type === 'action')).toHaveLength(1)
    expect(usePhantomStore.getState().status).toBe('complete')
    await expect(provider.decide(approval.id, 'approved', 'demo-operator', 'Retry')).rejects.toThrow()
    const replay = new MockAgentProvider()
    const replayed: AgentEvent[] = []
    replay.subscribe(event => replayed.push(event))
    await replay.investigate(task)
    expect(replayed).toEqual(events.slice(0, 4))
  })
  it('rejects live context and produces no action for a rejected approval', async () => {
    const provider = new MockAgentProvider()
    const events: AgentEvent[] = []
    provider.subscribe(event => events.push(event))
    await expect(provider.investigate({ ...task, context: { ...agentContext, provenance: 'LIVE' } })).rejects.toThrow()
    await provider.investigate(task)
    await provider.decide('approval-test-task', 'rejected', 'demo-operator', 'Insufficient evidence')
    expect(events.some(event => event.type === 'action')).toBe(false)
  })
  it('honors cancellation, subscription cleanup, disposal, and duplicate event delivery', async () => {
    const provider = new MockAgentProvider()
    const events: AgentEvent[] = []
    const unsubscribe = provider.subscribe(event => events.push(event))
    const controller = new AbortController()
    controller.abort()
    await provider.investigate(task, controller.signal)
    expect(events.at(-1)).toMatchObject({ type: 'status', status: 'cancelled' })
    const event = events[0]
    usePhantomStore.getState().receive(event)
    usePhantomStore.getState().receive(event)
    expect(usePhantomStore.getState().events).toHaveLength(1)
    unsubscribe()
    await provider.investigate({ ...task, id: 'another-task' })
    expect(events).toHaveLength(2)
    provider.dispose()
    await expect(provider.investigate({ ...task, id: 'disposed-task' })).rejects.toThrow()
  })
})
