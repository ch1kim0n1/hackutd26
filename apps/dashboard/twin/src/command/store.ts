import { create } from 'zustand'
import { advanceSimulation, changeSimulation, createInitialState, createOperatorIncident, decideApproval, injectObservation, requestReturnHome, requestWaypoint, retryInspection, setEmergencyStop } from './engine'
import { commandEventBus } from './event-bus'
import { AgentContextStore } from './agents'
import { createLiveDeps, LiveSync, mapSnapshot } from './live'
import type { LiveSnapshot } from './live/types'
import type { CommandState, CommandStore } from './model'

export const agentContextStore = new AgentContextStore()
const MODE_KEY = 'phantom-command-mode'
let liveSync: LiveSync | null = null

function storedMode(): 'demo' | 'live' {
  try { return localStorage.getItem(MODE_KEY) === 'live' ? 'live' : 'demo' } catch { return 'demo' }
}

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
  const liveOnly = () => get().mode === 'live'
  return {
    state: createInitialState(), workspace: 'overview', selectedId: null, camera: 'isometric',
    mode: 'demo', livePhase: 'off', liveDetail: '',
    setMode: mode => {
      liveSync?.stop(); liveSync = null
      if (mode === 'demo') {
        try { localStorage.setItem(MODE_KEY, 'demo') } catch { /* ignore */ }
        agentContextStore.clear()
        set({ mode: 'demo', livePhase: 'off', liveDetail: '', state: createInitialState(get().state.scenario), selectedId: null })
        return
      }
      try { localStorage.setItem(MODE_KEY, 'live') } catch { /* ignore */ }
      agentContextStore.clear()
      const { deps, problems } = createLiveDeps()
      const fatal = problems.length > 0 && deps.fixture !== true
      set({
        mode: 'live', livePhase: fatal ? 'error' : 'connecting',
        liveDetail: fatal ? problems.join(' · ') : 'connecting to backends…',
        state: { ...createInitialState('resolution'), simulation: 'paused' }, selectedId: null,
      })
      if (fatal) return
      liveSync = new LiveSync(deps, {
        onPhase: (phase, detail) => set({ livePhase: phase, liveDetail: detail }),
        onSnapshot: snapshot => get().applyLive(snapshot),
      })
      void liveSync.start()
    },
    applyLive: (snapshot: LiveSnapshot) => set(store => {
      if (store.mode !== 'live') return store
      const prev = store.state
      const { entities } = mapSnapshot(snapshot, prev.elapsed)
      const tag = snapshot.provenance === 'LIVE' ? 'LIVE' : 'REPLAY'
      const feedEvent = { id: 'live-feed', at: prev.elapsed, type: 'system.live', detail: `${tag} backend feed · ${snapshot.api.detail}` }
      return {
        state: {
          ...prev, ...entities,
          events: [feedEvent, ...entities.events].slice(-400),
          activity: entities.activity.slice(-200),
          simulation: 'paused' as const,
        },
      }
    }),
    navigate: workspace => {
      if (workspace === get().workspace) return
      set({ workspace, ...(workspace === 'overview' ? { camera: 'isometric' as const } : {}) })
    },
    select: selectedId => { set({ selectedId }); agentContextStore.select(get().state, selectedId) },
    setCamera: camera => set({ camera }),
    start: () => update(state => liveOnly() ? state : changeSimulation(state, 'start')),
    pause: () => update(state => liveOnly() ? { ...state, simulation: 'paused' } : changeSimulation(state, 'pause')),
    reset: scenario => { agentContextStore.clear(); set({ state: createInitialState(scenario ?? get().state.scenario), selectedId: null }) },
    setSpeed: speed => { if (Number.isFinite(speed) && speed >= 0.25 && speed <= 8) set({ state: { ...get().state, speed } }) },
    setScenario: scenario => { if (liveOnly() || !['patrol', 'unknown', 'impersonation', 'tamper', 'correlated', 'resolution'].includes(scenario)) return; agentContextStore.clear(); set({ state: createInitialState(scenario), selectedId: null }) },
    tick: seconds => update(state => liveOnly()
      ? { ...state, elapsed: state.elapsed + seconds }
      : advanceSimulation(state, seconds)),
    inject: kind => update(state => liveOnly() ? state : injectObservation(state, kind)),
    emergencyStop: () => { if (!liveOnly()) update(state => setEmergencyStop(state, true)) },
    releaseStop: () => { if (!liveOnly()) update(state => setEmergencyStop(state, false)) },
    returnHome: () => { if (!liveOnly()) update(requestReturnHome) },
    waypoint: (target, zoneId) => { if (!liveOnly()) update(state => requestWaypoint(state, target, zoneId)) },
    decideApproval: (approvalId, approve) => { if (!liveOnly()) update(state => decideApproval(state, approvalId, approve)) },
    createIncident: (title, zoneId, severity) => {
      if (liveOnly()) return
      const previous = get().state
      update(state => createOperatorIncident(state, title, zoneId, severity))
      if (get().state !== previous) get().select(get().state.incidents.at(-1)?.id ?? null)
    },
    retryInspection: incidentId => { if (!liveOnly()) update(state => retryInspection(state, incidentId)) },
  }
})

/** Restore persisted mode once at app boot (App calls this). */
export function restorePersistedMode(): void {
  if (storedMode() === 'live') useCommandStore.getState().setMode('live')
}
