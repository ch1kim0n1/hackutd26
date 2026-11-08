import { lazy, Suspense, useState, type RefObject } from 'react'
import { Activity, ArrowDownRight, ArrowUpRight, ArrowRight, Bot, Check, Crosshair, Expand, Grip, Radio, RotateCcw, Shield, ShieldAlert, Zap } from 'lucide-react'
import GridLayout, { useContainerWidth, type Layout } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useCommandStore } from '../store'
import { formatTime } from '../model'
import { AnimatedNumber, Panel, Sparkline, Status } from '../components/Primitives'
import TelemetryChart from '../components/TelemetryChart'

const TwinScene = lazy(() => import('../twin/TwinScene'))
const initialLayout: Layout = [
  { i: 'twin', x: 0, y: 0, w: 8, h: 9, minW: 5, minH: 7 },
  { i: 'intel', x: 8, y: 0, w: 4, h: 9, minW: 3, minH: 6 },
  { i: 'network', x: 0, y: 9, w: 5, h: 5, minW: 3, minH: 4 },
  { i: 'incidents', x: 5, y: 9, w: 4, h: 5, minW: 3, minH: 4 },
  { i: 'rover', x: 9, y: 9, w: 3, h: 5, minW: 3, minH: 4 },
]

function ActivityFeed() {
  const state = useCommandStore(s => s.state)
  const navigate = useCommandStore(s => s.navigate), select = useCommandStore(s => s.select)
  const reduced = useReducedMotion()
  return <div className="pc-intel-feed"><AnimatePresence initial={false}>{state.activity.slice(-6).reverse().map((item, index) => <motion.button layout={!reduced} initial={{ opacity: 0, y: reduced ? 0 : -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} key={item.id} className={`pc-feed-item ${index === 0 ? 'is-latest' : ''}`} onClick={() => { if (item.incidentId) select(item.incidentId); navigate('intelligence') }}>
    <span className={`pc-feed-icon ${item.kind === 'finding' ? 'pc-green' : item.kind === 'observation' ? 'pc-amber' : 'pc-cyan'}`}>{item.kind === 'finding' ? <Check size={13} /> : item.kind === 'observation' ? <Radio size={13} /> : <Zap size={13} />}</span><span><span className="pc-feed-meta"><b>{item.kind}</b><time>{formatTime(item.at).slice(0, 8)}</time></span><strong>{item.title}</strong><span className="pc-feed-detail">{item.detail}</span></span>
  </motion.button>)}</AnimatePresence></div>
}

export default function OverviewWorkspace() {
  const { state, navigate, select, setCamera } = useCommandStore()
  const [arrange, setArrange] = useState(false), [layout, setLayout] = useState<Layout>(initialLayout)
  const { width, containerRef, mounted } = useContainerWidth()
  const [metric, setMetric] = useState<'traffic' | 'latency'>('traffic')
  const active = state.incidents.filter(i => i.status !== 'resolved')
  const posture = Math.max(35, 98 - active.reduce((total, i) => total + (i.severity === 'critical' ? 15 : i.severity === 'high' ? 9 : 4), 0))
  const mission = state.missions.find(m => m.id === state.rover.missionId)
  const latest = state.telemetry.at(-1)
  const small = width < 850
  const computedLayout = small ? layout.map((item, index) => ({ ...item, x: 0, y: index * 8, w: 12, minW: 1, h: item.i === 'twin' ? 9 : item.i === 'intel' ? 7 : 5 })) : layout
  return <div className="pc-overview">
    <div className="pc-metrics">
      <div className="pc-metric"><span className="pc-metric-label"><Shield size={15} /> Security posture</span><div className="pc-metric-value"><AnimatedNumber value={posture} /><small>/100</small><Status tone={posture > 90 ? 'green' : 'amber'}>{posture > 90 ? 'Protected' : 'Investigating'}</Status></div><div className="pc-metric-bottom"><span className="pc-green"><ArrowUpRight size={12} /> Continuous assessment</span><Sparkline values={state.telemetry.map((s, i) => 80 + s.signals * .1 + i * .15)} color="#bfb6ab" /></div></div>
      <div className="pc-metric"><span className="pc-metric-label"><ShieldAlert size={15} /> Active incidents</span><div className="pc-metric-value"><AnimatedNumber value={active.length} /><small>open</small><span className={active.length ? 'pc-severity-tag' : 'pc-neutral-tag'}>{active.filter(i => i.severity === 'critical' || i.severity === 'high').length} high priority</span></div><div className="pc-metric-bottom"><span>{state.incidents.filter(i => i.status === 'resolved').length} resolved · all synthetic</span><button aria-label="View all incidents" onClick={() => navigate('incidents')}><ArrowUpRight size={16} /></button></div></div>
      <div className="pc-metric"><span className="pc-metric-label"><Radio size={15} /> Monitored devices</span><div className="pc-metric-value"><AnimatedNumber value={state.devices.length} /><small>entities</small><span className="pc-cyan pc-mono">3 ZONES</span></div><div className="pc-metric-bottom"><span><i className="pc-dot pc-green" /> {state.devices.filter(d => d.status === 'healthy').length} nominal</span><Sparkline values={state.telemetry.map(s => s.signals)} /></div></div>
      <div className="pc-metric"><span className="pc-metric-label"><Bot size={15} /> Intelligence engine</span><div className="pc-metric-value pc-engine-value">NEMOTRON <span className="pc-engine-dot" /></div><div className="pc-metric-bottom"><span className="pc-purple">Mock agent · {state.findings.length} findings</span><span className="pc-mono">{state.simulation === 'running' ? 'ACTIVE' : 'READY'}</span></div></div>
    </div>
    <div className="pc-workspace-tools"><span className="pc-eyebrow"><span className="pc-dot pc-cyan" /> Facility 01 <span className="pc-tool-divider">/</span> Dallas · Edge datacenter</span><div><button className={`pc-text-button ${arrange ? 'pc-cyan' : ''}`} onClick={() => setArrange(v => !v)}><Grip size={13} /> {arrange ? 'Lock panels' : 'Arrange panels'}</button>{arrange && <button className="pc-text-button" onClick={() => setLayout(initialLayout)}><RotateCcw size={12} /> Reset layout</button>}</div></div>
    <div ref={containerRef as RefObject<HTMLDivElement>} className={`pc-dashboard-grid ${arrange ? 'is-arranging' : ''}`} data-testid="command-grid">
      {mounted && <GridLayout width={width} layout={computedLayout} gridConfig={{ cols: 12, rowHeight: 35, margin: [14, 14], containerPadding: [0, 0] }} dragConfig={{ enabled: arrange && !small, handle: '.pc-drag' }} resizeConfig={{ enabled: arrange && !small }} onLayoutChange={next => { if (!small) setLayout(next) }}>
        <div key="twin"><Panel title="Facility digital twin" label="LIVE MODEL" drag actions={<button className="pc-text-button" onClick={() => { setCamera('isometric'); navigate('twin') }}>Explore twin <Expand size={13} /></button>} className="pc-twin-panel"><div className="pc-twin-topline"><Status tone="green">{state.simulation === 'running' ? 'Simulation live' : state.simulation === 'paused' ? 'Simulation paused' : 'Simulation ready'}</Status><span>01 / 03 ZONES</span></div><div className="pc-preview-scene"><Suspense fallback={<div className="pc-loading">Initializing facility geometry…</div>}><TwinScene compact /></Suspense></div><div className="pc-twin-bottomline"><span><i className="pc-legend-line pc-cyan" /> Infrastructure</span><span><i className="pc-legend-line pc-purple" /> Compute</span><span><i className="pc-legend-line pc-green" /> Phantom rover</span><button onClick={() => navigate('twin')}>Interactive view <ArrowUpRight size={12} /></button></div></Panel></div>
        <div key="intel"><Panel title="Nemotron intelligence" label="AUTONOMOUS" drag actions={<span className="pc-dot pc-purple" />} className="pc-ai-panel"><div className="pc-ai-summary"><div className="pc-ai-orb"><Bot size={22} /></div><div><strong>{active.length ? 'Investigation in progress' : 'All systems in context'}</strong><p>Observing. Correlating. Acting within policy.</p></div></div><ActivityFeed /><button className="pc-panel-link" onClick={() => navigate('intelligence')}>Open intelligence workspace <ArrowRight size={14} /></button></Panel></div>
        <div key="network"><Panel title="Network activity" drag actions={<select className="pc-inline-select" aria-label="Network chart metric" value={metric} onChange={e => setMetric(e.target.value as 'traffic' | 'latency')}><option value="traffic">Throughput</option><option value="latency">Latency</option></select>}><div className="pc-chart-summary"><strong><AnimatedNumber value={latest?.[metric] ?? 0} decimals={1} /> <small>{metric === 'traffic' ? 'Mbps' : 'ms'}</small></strong><span className="pc-cyan"><Activity size={12} /> Simulated RF telemetry</span></div><TelemetryChart samples={state.telemetry} metric={metric} /></Panel></div>
        <div key="incidents"><Panel title="Incident watch" drag actions={<button className="pc-text-button" onClick={() => navigate('incidents')}>View all <ArrowUpRight size={13} /></button>}><div className="pc-incident-watch">{state.incidents.slice(-3).reverse().map(incident => <button key={incident.id} onClick={() => { select(incident.id); navigate('incidents') }}><span className={`pc-incident-mark ${incident.status === 'resolved' ? 'pc-green' : 'pc-red'}`}>{incident.status === 'resolved' ? <Check size={15} /> : <ShieldAlert size={15} />}</span><span><b>{incident.title}</b><small>{incident.id.toUpperCase()} · {state.zones.find(z => z.id === incident.zoneId)?.name}</small></span><span className={`pc-watch-status ${incident.status === 'resolved' ? 'pc-green' : 'pc-amber'}`}>{incident.status}</span></button>)}{state.incidents.length === 0 && <div className="pc-clear-state"><Shield size={26} /><b>Perimeter clear</b><span>Automatic monitoring is ready.</span></div>}</div></Panel></div>
        <div key="rover"><Panel title="Phantom patrol" drag actions={<Crosshair size={14} className="pc-green" />}><div className="pc-rover-card"><div className="pc-rover-emblem"><svg viewBox="0 0 120 70" aria-hidden="true"><path d="M20 40 55 22 95 40 60 58Z M20 40V26L55 10 95 26V40 M55 10V22 M95 26 60 44 20 26 M60 44V58" /><path d="M38 18V6L52 1 65 8V16M38 6 52 13 65 8" /><path d="M25 37V47L36 53V43 M77 48V58L90 51V41" /></svg></div><div><Status tone={state.rover.stopped ? 'red' : 'green'}>{state.rover.stopped ? 'E-stop latched' : mission?.status.replace('_', ' ') ?? 'Standby'}</Status><p>{mission?.title ?? 'Ready for assignment'}</p></div></div><div className="pc-rover-mini-stats"><span><b>{state.rover.battery.toFixed(0)}<small>%</small></b>Battery</span><span><b>{state.rover.speed.toFixed(1)}<small>m/s</small></b>Velocity</span><span><b>{state.rover.distance.toFixed(0)}<small>m</small></b>Travelled</span></div><button className="pc-panel-link" onClick={() => navigate('rover')}>Rover operations <ArrowDownRight size={14} /></button></Panel></div>
      </GridLayout>}
    </div>
    <div className="pc-systems-strip"><span><Check size={12} /> Mock gateway <b>Nominal</b></span><span><Check size={12} /> Occupancy map <b>Loaded</b></span><span><Check size={12} /> Policy engine <b>Enforced</b></span><span><Check size={12} /> Event bus <b>{state.events.length} events</b></span><span className="pc-mono">ALL DATA SYNTHETIC</span></div>
  </div>
}
