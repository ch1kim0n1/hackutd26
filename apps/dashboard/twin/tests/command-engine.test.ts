import { beforeEach, describe, expect, it } from 'vitest'
import { advanceSimulation, changeSimulation, createInitialState, createOperatorIncident, decideApproval, injectObservation, isNavigable, planRoute, requestReturnHome, requestWaypoint, setEmergencyStop } from '../src/command/engine'
import { evaluatePolicy, MockAgentProvider, buildAgentContext, NemotronAgentProvider } from '../src/command/agents'
import { CommandEventBus, commandEventBus } from '../src/command/event-bus'
import { agentContextStore, useCommandStore } from '../src/command/store'
import type { ScenarioId } from '../src/command/model'

function run(scenario: ScenarioId, seconds = 90) { return advanceSimulation(changeSimulation(createInitialState(scenario), 'start'), seconds) }

describe('Phantom deterministic command engine', () => {
  it('replays every scenario exactly, with distinct fixtures and automatic investigations', () => {
    const scenarios: ScenarioId[] = ['patrol', 'unknown', 'impersonation', 'tamper', 'correlated', 'resolution']
    for (const scenario of scenarios) {
      const state = run(scenario)
      expect(state).toEqual(run(scenario))
      expect(state.devices).toHaveLength(32)
      expect(new Set(state.devices.map(device => device.id)).size).toBe(32)
      expect(state.zones).toHaveLength(3)
      expect(state.devices.filter(device => device.kind === 'server')).toHaveLength(12)
      expect(state.devices.filter(device => device.kind === 'ap')).toHaveLength(4)
      expect(state.devices.filter(device => device.kind === 'sensor')).toHaveLength(3)
      if (scenario === 'patrol') { expect(state.observations).toHaveLength(0); expect(state.missions.some(mission => mission.status === 'complete')).toBe(true) }
      else {
        expect(state.observations.length).toBeGreaterThan(0)
        expect(state.missions.some(mission => mission.type === 'investigate' && mission.status === 'complete')).toBe(true)
        expect(state.evidence.some(evidence => evidence.type === 'camera')).toBe(true)
        expect(state.evidence.some(evidence => evidence.type === 'lidar')).toBe(true)
        expect(state.findings.at(-1)?.confidence).toBeGreaterThan(0.9)
        expect(state.incidents.at(-1)?.status).toBe(scenario === 'impersonation' ? 'investigating' : 'resolved')
      }
    }
    const correlated = run('correlated').incidents.at(-1)!
    expect(correlated.observationIds).toHaveLength(2)
    expect(correlated.severity).toBe('critical')
  })
  it('performs the entire automatic observation → incident → mission → evidence → resolution chain without an AI prompt', () => {
    const initial = createInitialState()
    const state = advanceSimulation(changeSimulation(initial, 'start'), 90)
    const incident = state.incidents.at(-1)!
    expect(incident.status).toBe('resolved')
    expect(incident.timeline.map(entry => entry.kind)).toEqual(['observation', 'analysis', 'mission', 'evidence', 'evidence', 'resolution'])
    expect(state.events.map(event => event.type)).toEqual(expect.arrayContaining(['observation.received', 'incident.created', 'investigation.started', 'mission.started', 'mission.collecting', 'finding.created', 'incident.resolved', 'mission.complete']))
    expect(state.approvals).toHaveLength(0)
    expect(initial.elapsed).toBe(0)
    expect(initial.incidents).toHaveLength(1)
    const referenceIds = new Set(state.evidence.map(evidence => evidence.id))
    for (const finding of state.findings) for (const evidenceId of finding.evidenceIds) expect(referenceIds.has(evidenceId)).toBe(true)
  })
  it('uses a fixed clock so chunking and speed produce the same simulation', () => {
    const initial = changeSimulation(createInitialState(), 'start')
    const whole = advanceSimulation(initial, 40)
    let chunked = initial
    for (let i = 0; i < 400; i++) chunked = advanceSimulation(chunked, 0.1)
    expect(chunked).toEqual(whole)
    const fast = advanceSimulation({ ...initial, speed: 4 }, 10)
    expect({ ...fast, speed: 1 }).toEqual(whole)
    expect(advanceSimulation(initial, Number.NaN)).toBe(initial)
  })
  it('pauses all clock-driven work and preserves the independent E-stop through pause, resume and home', () => {
    const moving = advanceSimulation(changeSimulation(createInitialState(), 'start'), 8)
    expect(moving.rover.speed).toBeGreaterThan(0)
    const paused = changeSimulation(moving, 'pause')
    expect(advanceSimulation(paused, 30)).toBe(paused)
    let stopped = setEmergencyStop(moving, true)
    const position = stopped.rover.position
    stopped = advanceSimulation(stopped, 10)
    expect(stopped.rover.position).toEqual(position)
    expect(stopped.rover.speed).toBe(0)
    stopped = requestReturnHome(stopped)
    expect(stopped.rover.stopped).toBe(true)
    expect(stopped.missions.at(-1)?.status).toBe('queued')
    stopped = changeSimulation(stopped, 'pause')
    const released = setEmergencyStop(stopped, false)
    expect(released.simulation).toBe('paused')
    expect(advanceSimulation(released, 100).rover.position).toEqual(position)
    const returned = advanceSimulation(changeSimulation(released, 'start'), 90)
    expect(returned.rover.position).toEqual({ x: 18, y: 3 })
    expect(returned.missions.at(-1)?.status).toBe('complete')
  })
  it('requires a separate operator decision before a disruptive simulated action and deduplicates decisions', () => {
    const proposed = run('impersonation')
    expect(proposed.approvals).toHaveLength(1)
    expect(proposed.approvals[0].status).toBe('pending')
    expect(proposed.events.some(event => event.type === 'action.simulated')).toBe(false)
    const approved = decideApproval(proposed, proposed.approvals[0].id, true)
    expect(approved.events.filter(event => event.type === 'action.simulated')).toHaveLength(1)
    expect(approved.incidents.at(-1)?.status).toBe('resolved')
    expect(decideApproval(approved, proposed.approvals[0].id, true)).toBe(approved)
    const rejected = decideApproval(proposed, proposed.approvals[0].id, false)
    expect(rejected.events.some(event => event.type === 'action.simulated')).toBe(false)
    expect(rejected.incidents.at(-1)?.status).toBe('investigating')
  })
  it('counts only active capture time across E-stop and pause without publishing early evidence', () => {
    let state = changeSimulation(createInitialState(), 'start')
    for (let step = 0; step < 240 && !state.missions.some(mission => mission.status === 'collecting'); step++) state = advanceSimulation(state, 0.25)
    const missionId = state.rover.missionId!
    expect(state.missions.find(mission => mission.id === missionId)?.status).toBe('collecting')
    state = advanceSimulation(state, 1)
    const captureStarted = state.missions.find(mission => mission.id === missionId)?.collectingAt
    const evidenceCount = state.evidence.length
    const elapsed = state.elapsed
    state = advanceSimulation(setEmergencyStop(state, true), 10)
    expect(state.elapsed).toBe(elapsed + 10)
    expect(state.evidence).toHaveLength(evidenceCount)
    expect(state.missions.find(mission => mission.id === missionId)).toMatchObject({ status: 'collecting', collectionElapsed: 1, collectingAt: captureStarted })
    state = setEmergencyStop(changeSimulation(state, 'pause'), false)
    expect(advanceSimulation(state, 10)).toBe(state)
    state = advanceSimulation(changeSimulation(state, 'start'), 2.75)
    expect(state.evidence).toHaveLength(evidenceCount)
    expect(state.missions.find(mission => mission.id === missionId)?.status).toBe('collecting')
    state = advanceSimulation(state, 0.25)
    expect(state.missions.find(mission => mission.id === missionId)).toMatchObject({ status: 'complete', collectionElapsed: 4, collectingAt: captureStarted })
    expect(state.evidence).toHaveLength(evidenceCount + 3)
    expect(state.incidents.at(-1)?.status).toBe('resolved')
  })
  it('keeps every route segment navigable and constrains operator waypoints to the facility', () => {
    const route = planRoute({ x: 18, y: 3 }, { x: 1.5, y: 15 })
    for (let index = 1; index < route.length; index++) {
      const from = route[index - 1]; const to = route[index]
      for (let step = 0; step <= 20; step++) expect(isNavigable({ x: from.x + (to.x - from.x) * step / 20, y: from.y + (to.y - from.y) * step / 20 })).toBe(true)
    }
    const initial = createInitialState('patrol')
    expect(requestWaypoint(initial, { x: 999, y: 999 }).missions).toHaveLength(0)
    expect(evaluatePolicy('dispatch_inspection', initial, { x: NaN, y: 1 }).allowed).toBe(false)
    const queued = requestWaypoint(initial, { x: 3, y: 3 })
    expect(isNavigable(queued.missions[0].target)).toBe(true)
    const operatorIncident = createOperatorIncident(initial, 'Inspect maintenance cart', 'zone-operations', 'medium')
    const investigated = advanceSimulation(changeSimulation(operatorIncident, 'start'), 60)
    expect(investigated.incidents.at(-1)?.status).toBe('resolved')
  })
  it('processes manual event injection with the same automatic policy pipeline', () => {
    const state = injectObservation(createInitialState('patrol'), 'unknown')
    expect(state.observations).toHaveLength(1)
    expect(state.incidents).toHaveLength(1)
    const investigated = advanceSimulation(changeSimulation(state, 'start'), 120)
    expect(investigated.incidents.at(-1)?.status).toBe('resolved')
    expect(investigated.missions.some(mission => mission.type === 'investigate')).toBe(true)
  })
})

describe('command integration boundaries', () => {
  beforeEach(() => { useCommandStore.getState().reset(); commandEventBus.clear() })
  it('publishes selected operator-incident context immediately while the simulation is idle', () => {
    useCommandStore.getState().select('ap-03')
    useCommandStore.getState().createIncident('Operator inspection', 'zone-network', 'medium')
    const selectedId = useCommandStore.getState().selectedId
    expect(selectedId).toBe(useCommandStore.getState().state.incidents.at(-1)?.id)
    expect(agentContextStore.read()).toMatchObject({ selectedEntityId: selectedId, observation: null, activeIncidentIds: [selectedId] })
    useCommandStore.getState().select('ap-03')
    useCommandStore.getState().createIncident('  ', 'zone-network', 'medium')
    expect(useCommandStore.getState().selectedId).toBe('ap-03')
    expect(agentContextStore.read()?.selectedEntityId).toBe('ap-03')
  })
  it('publishes new typed events once, shares entity context and resets all state', () => {
    const events: string[] = []
    const unsubscribe = commandEventBus.subscribe(event => events.push(event.id))
    useCommandStore.getState().start(); useCommandStore.getState().tick(8)
    useCommandStore.getState().select('ble-04')
    expect(agentContextStore.read()?.selectedEntityId).toBe('ble-04')
    expect(events.length).toBeGreaterThan(5)
    expect(new Set(events).size).toBe(events.length)
    unsubscribe(); const count = events.length
    useCommandStore.getState().tick(40); expect(events).toHaveLength(count)
    useCommandStore.getState().reset()
    expect(useCommandStore.getState().state).toEqual(createInitialState())
    expect(useCommandStore.getState().selectedId).toBeNull()
    expect(agentContextStore.read()).toBeNull()
  })
  it('exposes a read-only structured inference boundary, never an actuator transport', async () => {
    const state = injectObservation(createInitialState(), 'unknown')
    const context = buildAgentContext(state, state.observations[0])
    const mock = new MockAgentProvider()
    const result = mock.assess(context)
    const future = new NemotronAgentProvider({ infer: async () => result })
    expect(await future.assess(context)).toEqual(result)
    const invalid = new NemotronAgentProvider({ infer: async () => ({ ...result, confidence: 3 }) })
    await expect(invalid.assess(context)).rejects.toThrow('Invalid structured')
    const bus = new CommandEventBus(); const delivered: string[] = []
    const unsub = bus.subscribe(event => delivered.push(event.id)); bus.publish(state.events[0]); unsub(); bus.publish(state.events[0])
    expect(delivered).toHaveLength(1)
  })
})

it('reassigns an interrupted inspection without clearing E-stop or changing the original incident time', async () => {
  const { retryInspection } = await import('../src/command/engine')
  let state = advanceSimulation(changeSimulation(createInitialState('impersonation'), 'start'), 8)
  const incidentId = state.incidents.at(-1)!.id, createdAt = state.incidents.at(-1)!.createdAt
  state = requestReturnHome(setEmergencyStop(state, true))
  state = retryInspection(state, incidentId)
  state = advanceSimulation(state, 10)
  expect(state.rover.stopped).toBe(true)
  expect(state.incidents.at(-1)?.createdAt).toBe(createdAt)
  state = advanceSimulation(setEmergencyStop(state, false), 90)
  expect(state.approvals.at(-1)?.status).toBe('pending')
  expect(state.missions.filter(m => m.incidentId === incidentId).at(-1)?.status).toBe('complete')
})

it('updates selected agent context before the first observation and never links an unrelated incident', () => {
  useCommandStore.getState().reset()
  useCommandStore.getState().select('ap-03')
  expect(agentContextStore.read()).toMatchObject({selectedEntityId:'ap-03',deviceIds:['ap-03'],observation:null})
})
