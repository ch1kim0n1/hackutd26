// Mock company dataset for the demo. All names, people, devices, and
// incidents are FICTIONAL and labeled SYNTHETIC. No real credentials,
// addresses, or personnel.

export const company = {
  name: 'Meridian Datacenters',
  tagline: 'Colocation and cloud infrastructure operator',
  facility: {
    id: 'PHX-1',
    name: 'Meridian PHX-1',
    city: 'Phoenix, AZ',
    floorAreaM2: 6200,
    racksTotal: 48,
    powerKw: 320,
    cooling: 'N+1 CRAH',
  },
  demoScenario: 'Unauthorized device + cabinet tamper inside a live customer row',
  provenance: 'SYNTHETIC' as const,
}

// Zone layout matches apps/dashboard/twin/src/main.jsx ZONES
// (x, y, w, d meters) so incident markers land on the twin map.
export interface MockZone {
  id: string
  name: string
  function: string
  bounds: { x: number; y: number; w: number; d: number }
  access: 'public' | 'staff' | 'restricted'
}

export const zones: MockZone[] = [
  { id: 'rack-01', name: 'Customer row A', function: '48U compute racks, enterprise colocation', bounds: { x: 2, y: 1, w: 2, d: 1.5 }, access: 'restricted' },
  { id: 'lab-b', name: 'Network lab B', function: 'Patch panels, test switches, staging gear', bounds: { x: -3, y: -2, w: 3, d: 2 }, access: 'staff' },
  { id: 'lobby', name: 'Lobby and check-in', function: 'Visitor ingress, badge readers, cameras', bounds: { x: 0, y: 4, w: 4, d: 2 }, access: 'public' },
  { id: 'bench-row', name: 'Engineer bench row', function: 'Workstations, consoles, asset staging', bounds: { x: -1, y: 0, w: 5, d: 1.5 }, access: 'staff' },
]

export interface MockDevice {
  id: string
  name: string
  kind: 'server' | 'network' | 'sensor' | 'rover' | 'ap' | 'ble'
  zoneId: string
  vendor: string
  role: string
}

export const devices: MockDevice[] = [
  { id: 'rack-01', name: 'SRV-A01', kind: 'server', zoneId: 'rack-01', vendor: 'Dell EMC', role: 'Customer hypervisor host' },
  { id: 'rack-02', name: 'SRV-A02', kind: 'server', zoneId: 'rack-01', vendor: 'Dell EMC', role: 'Customer hypervisor host' },
  { id: 'rack-03', name: 'SRV-A03', kind: 'server', zoneId: 'rack-01', vendor: 'HPE', role: 'Storage array controller' },
  { id: 'puck-a-01', name: 'WIFI-PUCK-A01', kind: 'ap', zoneId: 'rack-01', vendor: 'Phantom Sense', role: 'Wi-Fi + cabinet contact sensor' },
  { id: 'puck-b-01', name: 'CAB-PUCK-B01', kind: 'sensor', zoneId: 'rack-01', vendor: 'Phantom Sense', role: 'Reed contact + tamper beacon' },
  { id: 'puck-c-01', name: 'BLE-PUCK-C01', kind: 'ble', zoneId: 'rack-01', vendor: 'Phantom Sense', role: 'BLE asset beacon' },
  { id: 'sensor-lab-01', name: 'MON-LAB-01', kind: 'sensor', zoneId: 'lab-b', vendor: 'Phantom Sense', role: 'Environmental + door sensor' },
  { id: 'ap-lab-02', name: 'PHANTOM-AP-02', kind: 'ap', zoneId: 'lab-b', vendor: 'Aruba Networks', role: 'Managed lab access point' },
  { id: 'rover-01', name: 'PHANTOM / R-01', kind: 'rover', zoneId: 'lobby', vendor: 'Phantom Robotics', role: 'Autonomous patrol rover' },
  { id: 'switch-core-01', name: 'CORE-SW-01', kind: 'network', zoneId: 'lab-b', vendor: 'Arista', role: 'Top-of-rack aggregation' },
]

export interface MockIncident {
  id: string
  title: string
  zoneId: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'investigating' | 'contained' | 'resolved'
  openedAt: string
  summary: string
  timeline: { at: string; title: string; detail: string }[]
}

export const incidents: MockIncident[] = [
  {
    id: 'inc-demo-01',
    title: 'Rogue access point inside customer row A',
    zoneId: 'rack-01',
    severity: 'high',
    status: 'investigating',
    openedAt: '2026-11-07T18:04:00Z',
    summary: 'WIFI-PUCK-A01 detected an unclassified BSSID beaconing on channel 6 inside the restricted customer row. No matching asset record exists.',
    timeline: [
      { at: '2026-11-07T18:04:12Z', title: 'Unknown BSSID detected', detail: 'wifi_ap_seen event, RSSI -47 dBm, channel 6, inside rack-01 bounds.' },
      { at: '2026-11-07T18:04:31Z', title: 'Alert escalated to incident', detail: 'Deterministic correlation matched unknown-device rule; incident inc-demo-01 opened.' },
      { at: '2026-11-07T18:06:02Z', title: 'Rover dispatched for visual confirm', detail: 'Mission m-104 assigned to PHANTOM / R-01, waypoint tag-rack-a01.' },
      { at: '2026-11-07T18:09:47Z', title: 'Photo evidence captured', detail: 'capture_photo mission completed; image hash recorded as evidence ev-demo-01.' },
    ],
  },
  {
    id: 'inc-demo-02',
    title: 'Cabinet door contact opened in row A',
    zoneId: 'rack-01',
    severity: 'critical',
    status: 'open',
    openedAt: '2026-11-07T18:11:30Z',
    summary: 'Reed contact on SRV-A02 reports open outside any maintenance window. Correlated with the rogue AP incident.',
    timeline: [
      { at: '2026-11-07T18:11:30Z', title: 'Contact open event', detail: 'cabinet_contact_open from puck-b-01, no active maintenance window.' },
      { at: '2026-11-07T18:11:44Z', title: 'Correlated with inc-demo-01', detail: 'Same zone, overlapping window, physical + RF evidence chain.' },
    ],
  },
  {
    id: 'inc-demo-03',
    title: 'Scheduled maintenance access, operations',
    zoneId: 'lab-b',
    severity: 'low',
    status: 'resolved',
    openedAt: '2026-11-07T17:20:00Z',
    summary: 'Authorized contractor access during the 17:00-19:00 maintenance window. Closed after schedule match.',
    timeline: [
      { at: '2026-11-07T17:22:10Z', title: 'Door contact observed', detail: 'Access matched the published maintenance schedule for MON-LAB-01.' },
      { at: '2026-11-07T17:55:00Z', title: 'Access window confirmed', detail: 'No anomalies. Incident closed by on-call commander.' },
    ],
  },
]

export interface MockPerson {
  id: string
  name: string
  role: 'commander' | 'responder' | 'agent' | 'observer' | 'device'
  callsign: string
}

export const personnel: MockPerson[] = [
  { id: 'u-commander', name: 'Dana Whitfield', role: 'commander', callsign: 'IC-1' },
  { id: 'u-responder', name: 'Marcus Oyelaran', role: 'responder', callsign: 'IR-2' },
  { id: 'u-agent', name: 'NEMOTRON-AGENT', role: 'agent', callsign: 'AI-1' },
  { id: 'u-observer', name: 'Priya Raman', role: 'observer', callsign: 'OBS-3' },
  { id: 'u-gateway', name: 'COLLECTOR-GW', role: 'device', callsign: 'GW-1' },
  { id: 'u-rover', name: 'ROVER-01-PRINCIPAL', role: 'device', callsign: 'RV-1' },
]

export const network = {
  ssidCorp: 'MERIDIAN-CORP',
  ssidGuest: 'MERIDIAN-GUEST',
  rogueBssid: '02:11:22:33:44:55',
  rogueSsid: 'FREE-AIRPORT-WIFI',
  sensorSecretsNote: 'Per-device HMAC keys live in GATEWAY_DEVICE_HMAC_KEYS, not in this file.',
}
