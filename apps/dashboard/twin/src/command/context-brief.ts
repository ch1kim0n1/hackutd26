import type { CommandState } from './model'
import { formatTime } from './model'

/** A deterministic, read-only answer assembled exclusively from the shared demo records. */
export function contextBrief(state: CommandState, selectedId: string | null, question = ''): string {
  const selected = state.devices.find(d => d.id === selectedId)
  const incident = state.incidents.find(i => i.id === selectedId || i.deviceIds.includes(selectedId ?? '')) ?? (selected ? undefined : state.incidents.at(-1))
  const mission = state.missions.find(m => m.id === state.rover.missionId)
  const active = state.incidents.filter(i => i.status !== 'resolved')
  const base = `**DEMO context · ${formatTime(state.elapsed)} UTC**\n\n`
  if (/rover|battery|mission|position|stop|patrol/i.test(question)) return base + `Phantom–01 is ${state.rover.stopped ? 'halted by the independent emergency stop' : mission?.status.replaceAll('_', ' ') ?? 'in standby'} at (${state.rover.position.x.toFixed(1)}, ${state.rover.position.y.toFixed(1)}) m. Battery: ${state.rover.battery.toFixed(1)}%.\n\n${mission ? `Current mission: ${mission.title}.` : 'There is no active mission.'} All movement and sensor streams are simulated.`
  const selectedSummary = selected ? `Selected entity: **${selected.name}** (${selected.id}), ${selected.protocol}, ${selected.status}. Risk score ${selected.risk}/100.\n\n` : ''
  const finding = state.findings.filter(f => f.incidentId === incident?.id).at(-1)
  return base + selectedSummary + `${state.devices.length} monitored entities across ${state.zones.length} zones; ${active.length} active incidents; ${state.approvals.filter(a => a.status === 'pending').length} pending operator approvals.\n\n` + (incident ? `**${incident.title}** is ${incident.status}. ${incident.evidenceIds.length} linked evidence records.\n\n${finding ? `${finding.title}: ${finding.detail}` : 'The structured investigation is in progress; no conclusion has been published.'}` : selected ? 'No incident is linked to this selected entity.' : 'The facility baseline is clear.') + '\n\nThis read-only brief uses the current simulation records. No model endpoint or external action is connected.'
}
