import { create } from 'zustand'
import type { ActionApproval, AgentEvent, AgentFinding, AgentStatus } from '@/types/agent'

interface PhantomState {
  selectedDeviceId: string | null
  glow: boolean
  status: AgentStatus
  events: AgentEvent[]
  findings: AgentFinding[]
  approvals: ActionApproval[]
  selectDevice: (id: string | null) => void
  setGlow: (value: boolean) => void
  receive: (event: AgentEvent) => void
  resetAgent: () => void
}
const initialAgent = { status: 'idle' as AgentStatus, events: [] as AgentEvent[], findings: [] as AgentFinding[], approvals: [] as ActionApproval[] }
export const usePhantomStore = create<PhantomState>((set) => ({
  selectedDeviceId: null, glow: true, ...initialAgent,
  selectDevice: (selectedDeviceId) => set({ selectedDeviceId }),
  setGlow: (glow) => set({ glow }),
  receive: (event) => set(state => {
    if (state.events.some(existing => existing.id === event.id)) return state
    return {
      events: [...state.events, event],
      ...(event.type === 'status' ? { status: event.status } : {}),
      ...(event.type === 'finding' ? { findings: [...state.findings, event.finding] } : {}),
      ...(event.type === 'approval' ? { approvals: [...state.approvals.filter(a => a.id !== event.approval.id), event.approval] } : {}),
    }
  }),
  resetAgent: () => set(initialAgent),
}))
