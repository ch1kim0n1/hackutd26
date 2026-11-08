import type { AgentContext } from '@/types/agent'
import type { SecurityDevice } from '@/types/security'

export const FIXTURE_TIME = '2026-11-07T18:00:00.000Z'
export const devices: SecurityDevice[] = [
  { id: 'rack-01', name: 'Compute rack 01', kind: 'Server', zone: 'North hall', status: 'Healthy', address: '192.0.2.10', provenance: 'SYNTHETIC' },
  { id: 'rack-02', name: 'Compute rack 02', kind: 'Server', zone: 'North hall', status: 'Healthy', address: '192.0.2.11', provenance: 'SYNTHETIC' },
  { id: 'sensor-01', name: 'Cabinet sensor', kind: 'Sensor', zone: 'Lab A', status: 'Investigate', address: '192.0.2.20', provenance: 'SYNTHETIC' },
  { id: 'ap-unknown', name: 'Unclassified AP', kind: 'Access point', zone: 'Lab A', status: 'Unknown', address: '192.0.2.30', provenance: 'SYNTHETIC' },
  { id: 'rover-01', name: 'Survey rover', kind: 'Rover', zone: 'South aisle', status: 'Healthy', address: '192.0.2.40', provenance: 'SYNTHETIC' },
]

export const agentContext: AgentContext = {
  incidentId: 'demo-incident-01', deviceIds: ['sensor-01', 'ap-unknown'],
  evidenceIds: ['fixture-contact-01', 'fixture-radio-01'], provenance: 'SYNTHETIC',
}

export const telemetry = {
  time: ['18:00', '18:01', '18:02', '18:03', '18:04', '18:05', '18:06', '18:07'],
  packets: [24, 31, 27, 39, 46, 41, 33, 29],
  latency: [12, 14, 13, 21, 24, 20, 16, 15],
}
