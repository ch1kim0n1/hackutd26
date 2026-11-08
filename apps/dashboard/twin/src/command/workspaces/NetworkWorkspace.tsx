import { useEffect, useMemo, useRef, useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ICellRendererParams } from 'ag-grid-community'
import { Background, Controls, ReactFlow, type Edge, type Node } from '@xyflow/react'
import { Activity, ArrowUpRight, Bluetooth, Fingerprint, Network, Radio, Search, Server, ShieldAlert, Wifi } from 'lucide-react'
import { palette } from '@/styles/palette'
import { useCommandStore } from '../store'
import { formatTime, type Device } from '../model'
import { Empty, Metric, SignalChart, Status } from './security/shared'
import '@xyflow/react/dist/style.css'
import './security.css'

ModuleRegistry.registerModules([AllCommunityModule])
const gridTheme = themeQuartz.withParams({
  backgroundColor: '#0c1623', foregroundColor: palette.text, headerBackgroundColor: '#111e2e',
  borderColor: '#22364b', accentColor: palette.wall, fontFamily: 'Geist Variable, sans-serif',
  fontSize: 11, headerFontSize: 9, headerTextColor: palette.muted, rowBorder: { color: '#172a3c' },
  wrapperBorder: false, wrapperBorderRadius: 0, spacing: 5, oddRowBackgroundColor: '#0d1826',
})
const kindIcon = { ap: Wifi, ble: Bluetooth, wifi: Radio, server: Server, sensor: Activity, rover: Fingerprint }

export default function NetworkWorkspace() {
  const state = useCommandStore(store => store.state)
  const selectedId = useCommandStore(store => store.selectedId)
  const select = useCommandStore(store => store.select)
  const navigate = useCommandStore(store => store.navigate)
  const [query, setQuery] = useState('')
  const [protocol, setProtocol] = useState('all')
  const [status, setStatus] = useState('all')
  const grid = useRef<AgGridReact<Device>>(null)
  const selectedIncident = state.incidents.find(incident => incident.id === selectedId)
  const selectedDevice = state.devices.find(device => device.id === selectedId || selectedIncident?.deviceIds[0] === device.id) ?? state.devices.find(device => device.status === 'threat') ?? state.devices[0]
  const rows = useMemo(() => state.devices.filter(device => (protocol === 'all' || device.protocol === protocol) && (status === 'all' || device.status === status)), [state.devices, protocol, status])
  const columns = useMemo<ColDef<Device>[]>(() => [
    { field: 'name', headerName: 'DEVICE / IDENTITY', flex: 1.7, minWidth: 175, cellRenderer: ({ data }: ICellRendererParams<Device>) => { if (!data) return null; const Icon = kindIcon[data.kind]; return <span className="sec-grid-name"><Icon size={13} /><span>{data.name}</span></span> } },
    { field: 'protocol', headerName: 'PROTOCOL', width: 104 },
    { field: 'zoneId', headerName: 'ZONE', width: 118, valueFormatter: params => state.zones.find(zone => zone.id === params.value)?.code ?? params.value },
    { field: 'status', headerName: 'STATE', width: 112, cellRenderer: ({ value }: ICellRendererParams<Device>) => <Status value={String(value)} /> },
    { field: 'risk', headerName: 'RISK', width: 91, cellRenderer: ({ value }: ICellRendererParams<Device>) => <div className={`sec-risk ${Number(value) > 50 ? 'sec-risk-high' : ''}`}><span>{String(value)}</span><i style={{ width: `${Math.max(2, Number(value))}%` }} /></div> },
    { field: 'rssi', headerName: 'RSSI', width: 88, valueFormatter: params => `${params.value} dBm` },
    { field: 'address', headerName: 'ADDRESS', minWidth: 135, flex: 1 },
  ], [state.zones])
  useEffect(() => { grid.current?.api?.redrawRows() }, [selectedId])
  const topology = useMemo(() => {
    const nodes: Node[] = [{ id: 'network-core', position: { x: 490, y: 0 }, data: { label: <span className="sec-topology-core"><Network size={14} />PHANTOM CORE</span> }, style: { background: '#132c3c', borderColor: '#36cff4', color: palette.text, width: 160, fontSize: 10 }, selectable: false }]
    const edges: Edge[] = []
    state.zones.forEach((zone, zoneIndex) => {
      const zoneDevices = state.devices.filter(device => device.zoneId === zone.id)
      const anchor = zoneDevices.find(device => device.kind === 'ap') ?? zoneDevices[0]
      if (!anchor) return
      const children = zoneDevices.filter(device => device.id !== anchor.id)
      const items = [anchor, ...children]
      items.forEach((device, index) => {
        const selected = device.id === selectedDevice?.id || !!selectedIncident?.deviceIds.includes(device.id)
        const color = device.status === 'threat' ? palette.threat : selected ? palette.wall : device.kind === 'server' ? palette.infrastructure : '#34556c'
        nodes.push({ id: device.id, position: index === 0 ? { x: zoneIndex * 400 + 100, y: 95 } : { x: zoneIndex * 400 + ((index - 1) % 3) * 120, y: 185 + Math.floor((index - 1) / 3) * 75 }, data: { label: <span className="sec-topology-label"><i style={{ background: color }} />{device.name}</span> }, selected, style: { background: selected ? '#153146' : '#101d2c', borderColor: color, color: selected ? palette.text : '#a4b9cc', width: index === 0 ? 150 : 110, borderRadius: 4, fontSize: 9, padding: index === 0 ? 12 : 9 } })
        edges.push({ id: `edge-${device.id}`, source: index === 0 ? 'network-core' : anchor.id, target: device.id, style: { stroke: device.status === 'threat' ? palette.threat : '#2d4c63', strokeWidth: selected ? 1.7 : 1 }, type: 'smoothstep' })
      })
    })
    return { nodes, edges }
  }, [state.devices, state.zones, selectedDevice?.id, selectedIncident])
  const radioDevices = state.devices.filter(device => ['Wi-Fi', 'BLE'].includes(device.protocol))
  const suspicious = state.devices.filter(device => device.status !== 'healthy')
  const relatedFindings = state.findings.filter(finding => state.incidents.find(incident => incident.id === finding.incidentId)?.deviceIds.includes(selectedDevice?.id ?? ''))
  return <div className="sec-workspace" data-testid="network-workspace">
    <div className="sec-metrics">
      <Metric label="Observed identities" value={state.devices.length} detail="Across 3 monitored zones" icon={<Network size={16} />} />
      <Metric label="Wireless signals" value={radioDevices.length} detail={`${state.devices.filter(device => device.protocol === 'Wi-Fi').length} Wi-Fi · ${state.devices.filter(device => device.protocol === 'BLE').length} BLE`} icon={<Radio size={16} />} tone="purple" />
      <Metric label="Outside baseline" value={suspicious.length.toString().padStart(2, '0')} detail="Automatically correlated by Nemotron" icon={<ShieldAlert size={16} />} tone={suspicious.length ? 'red' : 'green'} />
      <Metric label="Monitoring coverage" value="100%" detail="4 access points · 3 sentinels" icon={<Activity size={16} />} tone="green" />
    </div>
    <div className="sec-inventory-layout">
      <section className="pc-panel sec-inventory"><div className="pc-panel-head"><div><span className="pc-eyebrow">RF INTELLIGENCE</span><h2>Device inventory</h2></div><span className="pc-chip">{rows.length} identities</span></div>
        <div className="sec-filterbar"><label className="sec-search"><Search size={14} /><input aria-label="Search network devices" placeholder="Search name, address, zone…" value={query} onChange={event => setQuery(event.target.value)} /></label><select aria-label="Filter devices by protocol" value={protocol} onChange={event => setProtocol(event.target.value)}><option value="all">All protocols</option>{['Wi-Fi', 'BLE', 'Ethernet', 'System'].map(value => <option key={value}>{value}</option>)}</select><select aria-label="Filter devices by status" value={status} onChange={event => setStatus(event.target.value)}><option value="all">All states</option><option value="healthy">Healthy</option><option value="watch">Watch</option><option value="threat">Threat</option></select></div>
        <div className="sec-device-grid" data-testid="command-device-grid"><AgGridReact<Device> ref={grid} theme={gridTheme} rowData={rows} columnDefs={columns} defaultColDef={{ sortable: true, resizable: true }} quickFilterText={query} getRowId={params => params.data.id} rowHeight={39} headerHeight={34} onRowClicked={event => event.data && select(event.data.id)} getRowClass={params => params.data && (params.data.id === selectedDevice?.id || selectedIncident?.deviceIds.includes(params.data.id)) ? 'sec-selected-row' : ''} animateRows={false} /></div>
        <div className="sec-panel-foot"><span><i className="sec-live-dot" />Deterministic RF observations</span><span>SELECT A ROW TO INSPECT</span></div>
      </section>
      <section className="pc-panel sec-device-inspect"><div className="pc-panel-head"><div><span className="pc-eyebrow">SIGNAL INSPECTOR</span><h2>{selectedDevice?.name ?? 'No device selected'}</h2></div><Radio size={17} /></div>{selectedDevice && <><div className="sec-device-meta"><Status value={selectedDevice.status} /><span className="sec-mono">{selectedDevice.protocol} / {selectedDevice.address}</span></div><div className="sec-signal-value"><strong>{selectedDevice.rssi}</strong><span>dBm<span>SIMULATED RSSI</span></span><div className="sec-risk-score"><b>{selectedDevice.risk}</b><small>RISK / 100</small></div></div><SignalChart device={selectedDevice} /><dl className="sec-facts"><div><dt>Fingerprint</dt><dd>{selectedDevice.vendor}</dd></div><div><dt>Location</dt><dd>{state.zones.find(zone => zone.id === selectedDevice.zoneId)?.name}</dd></div><div><dt>Last observed</dt><dd>{formatTime(selectedDevice.lastSeen)} UTC</dd></div></dl><button className="sec-text-button" onClick={() => { select(selectedDevice.id); navigate('twin') }}>Locate in digital twin<ArrowUpRight size={14} /></button></>}</section>
    </div>
    <div className="sec-network-bottom"><section className="pc-panel"><div className="pc-panel-head"><div><span className="pc-eyebrow">RELATIONSHIP MAP</span><h2>Network topology</h2></div><span className="pc-chip">Modeled connections</span></div><div className="sec-topology" data-testid="command-topology"><ReactFlow nodes={topology.nodes} edges={topology.edges} onNodeClick={(_, node) => node.id !== 'network-core' && select(node.id)} fitView fitViewOptions={{ padding: 0.1 }} minZoom={0.2} maxZoom={2} nodesDraggable={false} nodesConnectable={false} colorMode="dark" attributionPosition="bottom-right"><Background gap={24} color="#1c3246" /><Controls showInteractive={false} /></ReactFlow></div><div className="sec-panel-foot"><span><i className="sec-legend-dot sec-purple" />Infrastructure<i className="sec-legend-dot sec-cyan" />Selected<i className="sec-legend-dot sec-red" />Anomaly</span><span>CLICK NODE TO CORRELATE</span></div></section>
      <section className="pc-panel"><div className="pc-panel-head"><div><span className="pc-eyebrow">OBSERVATION STREAM</span><h2>Network activity</h2></div><Activity size={16} /></div><div className="sec-event-list">{state.events.slice(-7).reverse().map(event => <button key={event.id} className="sec-event" onClick={() => event.entityId && select(event.entityId)} disabled={!event.entityId}><span className="sec-event-time">{formatTime(event.at)}</span><span><b>{event.type.replaceAll('.', ' / ').replaceAll('_', ' ')}</b><span>{event.detail}</span></span><i /></button>)}{state.events.length === 0 && <Empty title="Baseline established" detail="Start the simulation to observe deterministic network activity." />}</div>{relatedFindings.length > 0 && <div className="sec-linked-finding"><span className="pc-eyebrow">CORRELATED FINDING</span><p>{relatedFindings.at(-1)?.title}</p><button className="sec-text-button" onClick={() => { select(relatedFindings.at(-1)!.incidentId); navigate('incidents') }}>Open incident<ArrowUpRight size={13} /></button></div>}</section></div>
  </div>
}
