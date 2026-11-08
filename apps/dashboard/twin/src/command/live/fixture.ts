import { emptyRows, type ApiSnapshot, type LiveRows, type LiveSnapshot } from './types'
import { toMicros } from './time'

/** Deterministic replay fixture: recorded backend-shaped rows emitted on
 * a timer so the live pipeline can be exercised without a running
 * stack (tests, offline demos). Everything produced is labelled
 * provenance 'REPLAY' — never LIVE (docs/13). */

const NOW = 1_760_000_000_000_000 // fixed epoch micros (~2025-10) for determinism

function ts(secondsAgo: number): number {
  return NOW - Math.round(secondsAgo * 1_000_000)
}

const FIXTURE_ROWS: LiveRows = {
  zones: [
    { id: 'rack-hall', name: 'Rack hall', boundsJson: '{"x":0,"y":0,"w":14,"h":18}', waypoints: '[]', updatedAt: ts(600) } as never,
    { id: 'network-core', name: 'Network core', boundsJson: '{"x":14,"y":9,"w":10,"h":9}', waypoints: '[]', updatedAt: ts(600) } as never,
    { id: 'ops-floor', name: 'Operations floor', boundsJson: '{"x":14,"y":0,"w":10,"h":9}', waypoints: '[]', updatedAt: ts(600) } as never,
  ],
  devices: [
    { id: 'puck-wifi-01', type: { tag: 'PuckWifi' }, zoneId: 'rack-hall', status: { tag: 'Online' }, lastSeen: ts(2), lastSeq: 41n, firmware: '0.1.0' } as never,
    { id: 'puck-ble-01', type: { tag: 'PuckBle' }, zoneId: 'rack-hall', status: { tag: 'Degraded' }, lastSeen: ts(4), lastSeq: 38n, firmware: '0.1.0' } as never,
    { id: 'kismet-01', type: { tag: 'Kismet' }, zoneId: 'network-core', status: { tag: 'Online' }, lastSeen: ts(1), lastSeq: 55n, firmware: '2024.09' } as never,
    { id: 'sdr-01', type: { tag: 'Sdr' }, zoneId: 'network-core', status: { tag: 'Online' }, lastSeen: ts(1), lastSeq: 52n, firmware: '1.0' } as never,
    { id: 'rover-01', type: { tag: 'Rover' }, zoneId: 'ops-floor', status: { tag: 'Online' }, lastSeen: ts(3), lastSeq: 21n, firmware: '0.3.0' } as never,
  ],
  assets: [],
  observations: [
    { id: 1n, eventId: 'evt-fixture-001', deviceId: 'puck-wifi-01', kind: 'wifi_observation', seq: 40n, observedAt: ts(8), receivedAt: ts(8), zoneId: 'rack-hall', dataJson: '{"ssid":"PHANTOM-NET","bssid":"aa:bb:cc:dd:ee:ff","rssi":-54}', trustTier: { tag: 'DeviceAsserted' }, traceId: 'trace-fixture-1' } as never,
    { id: 2n, eventId: 'evt-fixture-002', deviceId: 'puck-ble-01', kind: 'ble_observation', seq: 37n, observedAt: ts(20), receivedAt: ts(20), zoneId: 'rack-hall', dataJson: '{"address":"02:DE:AD:BE:EF:01","rssi":-71,"name":"unregistered-tag"}', trustTier: { tag: 'DeviceAsserted' }, traceId: 'trace-fixture-2' } as never,
    { id: 3n, eventId: 'evt-fixture-003', deviceId: 'kismet-01', kind: 'device_health', seq: 55n, observedAt: ts(2), receivedAt: ts(2), zoneId: 'network-core', dataJson: '{"component":"capture","status":"ok"}', trustTier: { tag: 'GatewayValidated' }, traceId: 'trace-fixture-3' } as never,
  ],
  incidents: [
    { id: 'inc-fixture-001', title: 'Unregistered BLE transmitter near rack hall', description: 'Fixture replay incident', severity: { tag: 'Medium' }, confidence: 0.8, status: { tag: 'Investigating' }, commanderId: 'admin', createdAt: ts(90), updatedAt: ts(30), version: 2n, traceId: 'trace-fixture-inc' } as never,
  ],
  evidence: [
    { id: 'evd-fixture-001', incidentId: 'inc-fixture-001', source: 'rf-scan', observedAt: ts(60), storageRef: 'lab://evidence/evd-fixture-001', sha256: 'a'.repeat(64), trustTier: { tag: 'DeviceAsserted' }, traceId: 'trace-fixture-ev' } as never,
  ],
  missions: [],
  approvals: [],
  actions: [],
  scopeEntries: [
    { id: 'scope-fixture-001', incidentId: 'inc-fixture-001', assetId: 'rack-hall', datasetCategory: 'customer-records', impactDimensions: [{ tag: 'Confidentiality' }], impactStatuses: [{ tag: 'SuspectedExposed' }], estimatedRecords: 1200n, evidenceRefs: ['ev-evd-fixture-001'], reviewer: 'operator', note: 'Fixture scope estimate', updatedAt: ts(45), version: 1n } as never,
  ],
  alerts: [
    { id: 'alert-fixture-001', ruleId: 'ble-unknown-device', observationIds: [2n], severity: { tag: 'Medium' }, state: { tag: 'Open' }, incidentId: 'inc-fixture-001', title: 'Unregistered BLE device observed', createdAt: ts(85), updatedAt: ts(30), version: 1n, traceId: 'trace-fixture-alert' } as never,
  ],
  auditEvents: [
    { id: 'aud-fixture-001', actor: 'system', operation: 'incident_created', entity: 'inc-fixture-001', incidentId: 'inc-fixture-001', beforeHash: '', afterHash: 'b'.repeat(64), detailJson: '{"source":"correlation"}', at: ts(90), traceId: 'trace-fixture-aud' } as never,
    { id: 'aud-fixture-002', actor: 'commander', operation: 'investigation_started', entity: 'inc-fixture-001', incidentId: 'inc-fixture-001', beforeHash: '', afterHash: 'c'.repeat(64), detailJson: '{"by":"operator"}', at: ts(40), traceId: 'trace-fixture-aud2' } as never,
  ],
  health: [],
  rfFrames: [],
}

const FIXTURE_API: ApiSnapshot = {
  reachable: true,
  detail: 'REPLAY fixture API · 1 incident · 1 investigation',
  incidentCount: 1,
  investigations: [{
    incident_id: 'api-incident-1', by: 'nemotron', brief: 'fixture brief', run_index: 0,
    assessment: { title: 'Fixture assessment', severity: 'medium', confidence: 0.7, summary: 'REPLAY · recorded investigation output', requestIsolation: false },
  }],
}

export function fixtureSnapshot(): LiveSnapshot {
  return { provenance: 'REPLAY', rows: FIXTURE_ROWS, api: FIXTURE_API, backendNowMicros: Number(NOW) }
}

export { toMicros }
