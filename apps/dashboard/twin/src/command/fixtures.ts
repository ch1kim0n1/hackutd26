import type { CommandState, Device, Point, ScenarioId, Zone } from './model'

export const HOME: Point = { x: 18, y: 3 }
export const ZONES: Zone[] = [
  { id: 'zone-server', name: 'Server hall', code: 'A', bounds: [0, 0, 14, 18], position: { x: 7, y: 9 }, color: '#a8a29e' },
  { id: 'zone-network', name: 'Network core', code: 'B', bounds: [14, 9, 24, 18], position: { x: 19, y: 13.5 }, color: '#eab308' },
  { id: 'zone-operations', name: 'Operations', code: 'C', bounds: [14, 0, 24, 9], position: { x: 19, y: 4.5 }, color: '#bfb6ab' },
]
const pad = (n: number) => String(n).padStart(2, '0')
function device(id: string, name: string, kind: Device['kind'], zoneId: string, position: Point, index: number): Device {
  const protocol = kind === 'ble' ? 'BLE' : kind === 'ap' || kind === 'wifi' ? 'Wi-Fi' : kind === 'rover' ? 'System' : 'Ethernet'
  const rssi = kind === 'ble' ? -58 - index % 12 : -36 - index % 18
  return { id, name, kind, zoneId, position, status: 'healthy', protocol, address: protocol === 'BLE' ? `02:DE:00:00:00:${pad(index)}` : `192.0.2.${index + 10}`, vendor: kind === 'rover' ? 'Phantom Robotics' : kind === 'server' ? 'Dell EMC' : kind === 'ap' ? 'Aruba Networks' : kind === 'sensor' ? 'Phantom Sense' : kind === 'ble' ? 'Nordic Semiconductor' : 'Intel Corporate', risk: 2 + index % 8, rssi, lastSeen: 0, signalHistory: Array.from({ length: 24 }, (_, i) => rssi + Math.round(Math.sin((i + index) * 0.7) * 3)) }
}
export function createDevices(): Device[] {
  const racks = Array.from({ length: 12 }, (_, i) => device(`rack-${pad(i + 1)}`, `SRV-${pad(i + 1)}`, 'server', 'zone-server', { x: [3, 7, 11][i % 3], y: [3, 7, 11, 15][Math.floor(i / 3)] }, i + 1))
  const aps = [{ x: 2, y: 1.5 }, { x: 12, y: 16.5 }, { x: 21, y: 14 }, { x: 21, y: 6 }].map((p, i) => device(`ap-${pad(i + 1)}`, `PHANTOM-AP-${pad(i + 1)}`, 'ap', i < 2 ? 'zone-server' : i === 2 ? 'zone-network' : 'zone-operations', p, i + 13))
  const sensors = [{ x: 1, y: 8 }, { x: 20, y: 16 }, { x: 18, y: 2 }].map((p, i) => device(`sensor-${pad(i + 1)}`, `MON-${pad(i + 1)}`, 'sensor', ['zone-server', 'zone-network', 'zone-operations'][i], p, i + 17))
  const wifi = Array.from({ length: 8 }, (_, i) => device(`wifi-${pad(i + 1)}`, ['OPS-CONSOLE', 'ENGINEERING-01', 'ENGINEERING-02', 'MGMT-TERMINAL', 'EDGE-GATEWAY', 'ENV-CONTROLLER', 'PHANTOM-TAB', 'LAB-CLIENT'][i], 'wifi', i < 4 ? 'zone-operations' : 'zone-network', { x: 16 + i % 4 * 1.7, y: i < 4 ? 5.5 : 11.5 }, i + 21))
  const ble = Array.from({ length: 4 }, (_, i) => device(`ble-${pad(i + 1)}`, ['TEMP-BEACON-01', 'ASSET-TAG-02', 'DOOR-BEACON-03', 'SERVICE-TAG-04'][i], 'ble', 'zone-server', { x: 1.5, y: 3 + i * 4 }, i + 29))
  return [...racks, ...aps, ...sensors, device('rover-01', 'PHANTOM / R-01', 'rover', 'zone-operations', { ...HOME }, 20), ...wifi, ...ble]
}
export function createInitialState(scenario: ScenarioId = 'resolution'): CommandState {
  return {
    elapsed: 0, speed: 1, simulation: 'ready', scenario, zones: structuredClone(ZONES), devices: createDevices(), observations: [],
    incidents: [{ id: 'incident-baseline', title: 'Scheduled access verification', severity: 'low', status: 'resolved', zoneId: 'zone-operations', deviceIds: ['sensor-03'], observationIds: [], evidenceIds: ['evidence-baseline'], findingIds: ['finding-baseline'], createdAt: -420, updatedAt: -120, timeline: [{ id: 'timeline-baseline-1', at: -420, title: 'Door contact observed', detail: 'Replay fixture: scheduled access in operations.', kind: 'observation' }, { id: 'timeline-baseline-2', at: -120, title: 'Access window confirmed', detail: 'Historical demo record closed after matching the maintenance schedule.', kind: 'resolution' }] }],
    evidence: [{ id: 'evidence-baseline', incidentId: 'incident-baseline', type: 'policy', at: -130, summary: 'Synthetic maintenance schedule authorizes the operations access window.' }],
    findings: [{ id: 'finding-baseline', incidentId: 'incident-baseline', at: -120, title: 'Scheduled maintenance confirmed', detail: 'The contact event matches an authorized service window. No further action is required in this replay fixture.', confidence: 0.98, evidenceIds: ['evidence-baseline'] }],
    activity: [{ id: 'agent-baseline-1', at: -120, kind: 'finding', title: 'Previous investigation resolved', detail: 'Scheduled operations access matched the synthetic maintenance record.', incidentId: 'incident-baseline' }, { id: 'agent-baseline-2', at: 0, kind: 'status', title: 'Nemotron mock agent standing by', detail: 'Event-driven analysis ready. Start simulation to stream deterministic observations.' }],
    missions: [], approvals: [], events: [{ id: 'event-baseline', at: 0, type: 'system.ready', detail: 'DEMO MODE · fixture loaded · no external services connected' }],
    rover: { position: { ...HOME }, heading: Math.PI, speed: 0, battery: 94, stopped: false, missionId: null, distance: 0, lidar: Array.from({ length: 72 }, (_, i) => 2.6 + Math.sin(i * 0.53) * 0.8 + Math.cos(i * 0.19) * 0.6) },
    twinFeed: { maps: [], anchors: [] },
    telemetry: Array.from({ length: 40 }, (_, i) => ({ at: i - 39, traffic: Math.round(38 + Math.sin(i * 0.41) * 9 + Math.cos(i * 0.17) * 5), signals: 31 + i % 3, cpu: 24 + Math.round(Math.sin(i * 0.29) * 5), latency: 12 + Math.round(Math.cos(i * 0.31) * 3) })), sequence: 1, scenarioStep: 0, tickRemainder: 0,
  }
}
