import { create } from 'zustand'
import { advanceSimulation, changeSimulation, createInitialState, createOperatorIncident, decideApproval, injectObservation, requestReturnHome, requestWaypoint, retryInspection, setEmergencyStop } from './engine'
import { commandEventBus } from './event-bus'
import { AgentContextStore } from './agents'
import type { CommandState, CommandStore } from './model'

export const agentContextStore = new AgentContextStore()
export const useCommandStore = create<CommandStore>((set, get) => {
  const update = (transform: (state: CommandState) => CommandState) => {
    const previous = get().state; const next = transform(previous)
    if (previous === next) return
    set({ state: next })
    const previousEvents = new Set(previous.events.map(event => event.id))
    for (const event of next.events) if (!previousEvents.has(event.id)) commandEventBus.publish(event)
    const observation = next.observations.at(-1)
    if (get().selectedId) agentContextStore.select(next, get().selectedId)
    else if (observation) agentContextStore.update(next, observation, null)
  }
  return {
    state: createInitialState(), workspace: 'overview', selectedId: null, camera: 'isometric',
    navigate: workspace => {
      if (workspace === get().workspace) return
      set({ workspace, ...(workspace === 'overview' ? { camera: 'isometric' as const } : {}) })
    },
    select: selectedId => { set({ selectedId }); agentContextStore.select(get().state, selectedId) },
    setCamera: camera => set({ camera }),
    start: () => update(state => changeSimulation(state, 'start')),
    pause: () => update(state => changeSimulation(state, 'pause')),
    reset: scenario => { agentContextStore.clear(); set({ state: createInitialState(scenario ?? get().state.scenario), selectedId: null }) },
    setSpeed: speed => { if (Number.isFinite(speed) && speed >= 0.25 && speed <= 8) set({ state: { ...get().state, speed } }) },
    setScenario: scenario => { if (!['patrol', 'unknown', 'impersonation', 'tamper', 'correlated', 'resolution'].includes(scenario)) return; agentContextStore.clear(); set({ state: createInitialState(scenario), selectedId: null }) },
    tick: seconds => update(state => advanceSimulation(state, seconds)),
    inject: kind => update(state => injectObservation(state, kind)),
    emergencyStop: () => update(state => setEmergencyStop(state, true)),
    releaseStop: () => update(state => setEmergencyStop(state, false)),
    returnHome: () => update(requestReturnHome),
    waypoint: (target, zoneId) => update(state => requestWaypoint(state, target, zoneId)),
    decideApproval: (approvalId, approve) => update(state => decideApproval(state, approvalId, approve)),
    createIncident: (title, zoneId, severity) => {
      const previous = get().state
      update(state => createOperatorIncident(state, title, zoneId, severity))
      if (get().state !== previous) get().select(get().state.incidents.at(-1)?.id ?? null)
    },
    retryInspection: incidentId => update(state => retryInspection(state, incidentId)),
  }
})
