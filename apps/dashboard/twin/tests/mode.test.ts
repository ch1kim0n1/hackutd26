import { beforeEach, describe, expect, it } from 'vitest'
import { useCommandStore } from '../src/command/store'
import { createInitialState } from '../src/command/engine'
import { fixtureSnapshot } from '../src/command/live/fixture'

describe('mode switch', () => {
  beforeEach(() => {
    useCommandStore.getState().setMode('demo')
  })

  it('defaults to demo mode with working simulation', () => {
    const s = useCommandStore.getState()
    expect(s.mode).toBe('demo')
    expect(s.state.devices.length).toBeGreaterThan(20)
    s.start()
    const before = useCommandStore.getState().state.elapsed
    useCommandStore.getState().tick(1)
    expect(useCommandStore.getState().state.elapsed).toBeGreaterThan(before)
  })

  it('applyLive replaces demo entities wholesale with backend data', () => {
    const store = useCommandStore.getState()
    store.setMode('demo')
    useCommandStore.setState({ mode: 'live', livePhase: 'online' })
    store.applyLive(fixtureSnapshot())
    const s = useCommandStore.getState().state
    expect(s.devices.map(d => d.id)).toContain('puck-wifi-01')
    expect(s.devices.map(d => d.id)).not.toContain('rack-01')
    expect(s.incidents.map(i => i.id)).toContain('inc-fixture-001')
    expect(s.observations[0].detail).toMatch(/^REPLAY · /)
    expect(s.events.some(e => e.id === 'live-feed')).toBe(true)
  })

  it('live tick advances the clock without running the scenario engine', () => {
    useCommandStore.setState({ mode: 'live' })
    const s0 = useCommandStore.getState().state
    useCommandStore.getState().tick(2)
    const s1 = useCommandStore.getState().state
    expect(s1.elapsed).toBe(s0.elapsed + 2)
    expect(s1.observations).toEqual(s0.observations)
    expect(s1.scenarioStep).toBe(s0.scenarioStep)
  })

  it('demo-mutating commands are inert in live mode', () => {
    useCommandStore.setState({ mode: 'live' })
    const before = useCommandStore.getState().state
    useCommandStore.getState().inject('unknown')
    useCommandStore.getState().emergencyStop()
    useCommandStore.getState().createIncident('x', 'zone-operations', 'low')
    useCommandStore.getState().decideApproval('appr-x', true)
    useCommandStore.getState().setScenario('patrol')
    const after = useCommandStore.getState().state
    expect(after.observations).toEqual(before.observations)
    expect(after.rover.stopped).toBe(before.rover.stopped)
    expect(after.incidents).toEqual(before.incidents)
    expect(after.scenario).toBe(before.scenario)
  })

  it('applyLive is a no-op outside live mode', () => {
    const before = useCommandStore.getState().state
    useCommandStore.getState().applyLive(fixtureSnapshot())
    expect(useCommandStore.getState().state).toBe(before)
  })

  it('setMode(demo) restores a clean simulation state', () => {
    useCommandStore.setState({ mode: 'live' })
    useCommandStore.getState().applyLive(fixtureSnapshot())
    useCommandStore.getState().setMode('demo')
    const s = useCommandStore.getState()
    expect(s.mode).toBe('demo')
    expect(s.state.devices.some(d => d.id === 'puck-wifi-01')).toBe(false)
    expect(s.state.devices.length).toBeGreaterThan(20)
  })
})
