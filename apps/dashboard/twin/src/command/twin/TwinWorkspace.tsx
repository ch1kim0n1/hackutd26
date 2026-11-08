import { Activity, ArrowUpRight, Box, Check, CircleDot, Layers, Radio, Server, ShieldAlert, Zap } from 'lucide-react'
import { useCommandStore } from '../store'
import TwinScene from './TwinScene'
import './twin.css'

export default function TwinWorkspace() {
  const state = useCommandStore(s => s.state)
  const selectedId = useCommandStore(s => s.selectedId)
  const select = useCommandStore(s => s.select)
  const navigate = useCommandStore(s => s.navigate)
  const device = state.devices.find(item => item.id === selectedId)
  const incident = state.incidents.find(item => item.id === selectedId)
  const zone = state.zones.find(item => item.id === (device?.zoneId ?? incident?.zoneId ?? selectedId))
  const hardware = state.devices.filter(item => ['server', 'ap', 'sensor', 'rover'].includes(item.kind))
  const active = state.incidents.filter(item => item.status !== 'resolved')
  const feed = state.twinFeed
  const primaryMap = feed.maps.find(m => m.registered) ?? feed.maps[0]
  return <div className="twin-workspace">
    <section className="twin-main-panel"><div className="twin-panel-heading"><div><Box size={15} /><strong>Facility digital twin</strong><span>LIVE SIMULATION</span></div><span className="twin-micro-copy">24 × 18 M <i>/</i> 3 SECURITY ZONES</span></div><div className="twin-workspace-canvas"><TwinScene /></div><div className="twin-legend"><span><i style={{ background: '#eab308' }} />Structure</span><span><i style={{ background: '#a8a29e' }} />Infrastructure</span><span><i style={{ background: '#bfb6ab' }} />Rover / route</span><span><i style={{ background: '#ef4444' }} />Active incident</span><em>Drag to orbit · Scroll to zoom · Click to inspect</em></div></section>
    <aside className="twin-inspector">
      <section className="twin-inspector-section"><div className="twin-section-title"><CrosshairIcon />ENTITY INSPECTOR <span>{selectedId ? 'SELECTED' : 'READY'}</span></div><h3>{device?.name ?? incident?.title ?? zone?.name ?? 'Facility A · Level 01'}</h3><p>{selectedId ? `${zone?.name ?? 'Facility'} · ${selectedId.toUpperCase()}` : 'Select equipment, a zone, or an incident to synchronize the command center.'}</p>
        <div className="twin-inspector-metrics"><div><span>STATE</span><strong className={device?.status === 'threat' || incident ? 'twin-red' : 'twin-green'}>{device?.status ?? incident?.status ?? 'MONITORING'}</strong></div><div><span>{device ? 'RISK SCORE' : 'ACTIVE INCIDENTS'}</span><strong>{device ? `${device.risk}/100` : active.length}</strong></div><div><span>POSITION</span><strong>{device ? `${device.position.x.toFixed(1)}, ${device.position.y.toFixed(1)}` : zone ? `${zone.position.x}, ${zone.position.y}` : '24 × 18 M'}</strong></div><div><span>{device ? 'PROTOCOL' : 'MAP RESOLUTION'}</span><strong>{device?.protocol ?? '0.25 M'}</strong></div></div>
        {device && <button className="twin-inspector-action" onClick={() => navigate(device.kind === 'rover' ? 'rover' : 'network')}>Open {device.kind === 'rover' ? 'rover operations' : 'network intelligence'}<ArrowUpRight size={14} /></button>}
        {incident && <button className="twin-inspector-action" onClick={() => navigate('incidents')}>Open incident timeline<ArrowUpRight size={14} /></button>}
      </section>
      <section className="twin-inspector-section"><div className="twin-section-title"><Layers size={13} />SPATIAL FEED <span>{feed.maps.length ? `${feed.maps.length} MAP${feed.maps.length > 1 ? 'S' : ''}` : 'NONE'}</span></div>
        {primaryMap ? <>
          <div className="twin-inspector-metrics">
            <div><span>FRAME</span><strong>{primaryMap.frameId.toUpperCase()}</strong></div>
            <div><span>REVISION</span><strong>#{primaryMap.revision}</strong></div>
            <div><span>GRID</span><strong>{primaryMap.width}×{primaryMap.height} @ {primaryMap.resolutionM} M</strong></div>
            <div><span>PROVENANCE</span><strong className={primaryMap.provenance === 'LIVE' ? 'twin-green' : 'twin-amber'}>{primaryMap.stale ? 'STALE' : primaryMap.provenance}</strong></div>
          </div>
          <p className="twin-feed-note">{primaryMap.registered ? 'Registered frame — geometry shares the facility coordinate system.' : 'Unregistered frame — boundary shown only; coordinates are not silently transformed.'} Heights are inferred visualization estimates, not LiDAR measurements.</p>
          <div className="twin-anchor-count">{feed.anchors.length} registered anchor{feed.anchors.length === 1 ? '' : 's'} · {state.devices.filter(d => d.kind === 'rover').length} rover target{state.devices.filter(d => d.kind === 'rover').length === 1 ? '' : 's'}</div>
        </> : <p className="twin-feed-note">No occupancy contract received yet. Simulated feed activates in demo mode; live mode consumes contract payloads from observations or the configured twin endpoint.</p>}
      </section>
      <section className="twin-inspector-section"><div className="twin-section-title"><ShieldAlert size={13} />SECURITY ZONES</div><div className="twin-zone-list">{state.zones.map(item => { const threats = active.filter(issue => issue.zoneId === item.id); return <button className={zone?.id === item.id ? 'is-selected' : ''} key={item.id} onClick={() => select(item.id)}><span className="twin-zone-code">{item.code}</span><span>{item.name}<small>{state.devices.filter(entry => entry.zoneId === item.id).length} tracked entities</small></span><span className={threats.length ? 'twin-red' : 'twin-green'}>{threats.length ? <ShieldAlert size={15} /> : <Check size={15} />}</span></button> })}</div></section>
      <section className="twin-inspector-section twin-entity-section"><div className="twin-section-title"><Radio size={13} />FACILITY ENTITIES <span>{hardware.length}</span></div><div className="twin-entity-list">{hardware.map(item => { const Icon = item.kind === 'server' ? Server : item.kind === 'ap' ? Radio : item.kind === 'rover' ? Zap : Activity; return <button key={item.id} aria-label={`Select ${item.name}`} aria-pressed={selectedId === item.id} onClick={() => select(item.id)}><Icon size={13} /><span>{item.name}</span><CircleDot size={10} className={item.status === 'threat' ? 'twin-red' : item.status === 'watch' ? 'twin-amber' : 'twin-green'} /></button> })}</div></section>
    </aside>
  </div>
}

function CrosshairIcon() { return <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="4.5" stroke="currentColor" /><path d="M8 0v5m0 6v5M0 8h5m6 0h5" stroke="currentColor" /></svg> }
