import { ArrowUpRight, Box, Network, ShieldAlert, X } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useCommandStore } from '../store'
import { formatTime } from '../model'
import { Sparkline, Status } from './Primitives'

export default function SelectionDetails() {
  const { state, selectedId, select, navigate, workspace } = useCommandStore()
  const device = state.devices.find(d => d.id === selectedId)
  const incident = state.incidents.find(i => i.id === selectedId)
  const reduced = useReducedMotion()
  const visible = device && workspace === 'overview'
  return <AnimatePresence>{visible && <motion.aside className="pc-inspector" aria-label="Selected device details" initial={{ opacity: 0, x: reduced ? 0 : 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reduced ? 0 : 24 }}>
    <header><span className="pc-eyebrow">Entity inspector</span><button className="pc-icon-button" aria-label="Close device details" onClick={() => select(null)}><X size={17} /></button></header>
    <div className="pc-inspector-heading"><Box size={26} /><div><h2>{device.name}</h2><p className="pc-mono pc-muted">{device.id}</p></div></div>
    <Status tone={device.status === 'healthy' ? 'green' : 'amber'}>{device.status}</Status>
    <dl className="pc-definition"><div><dt>Location</dt><dd>{state.zones.find(z => z.id === device.zoneId)?.name}</dd></div><div><dt>Protocol</dt><dd>{device.protocol}</dd></div><div><dt>Identity</dt><dd>{device.vendor}</dd></div><div><dt>Address</dt><dd>{device.address}</dd></div><div><dt>Threat score</dt><dd className={device.risk > 50 ? 'pc-red' : 'pc-green'}>{device.risk} / 100</dd></div><div><dt>Observed</dt><dd>{formatTime(device.lastSeen)} UTC</dd></div></dl>
    <div className="pc-inspector-signal"><span className="pc-eyebrow">Signal history · {device.rssi} dBm</span><Sparkline values={device.signalHistory} /></div>
    <p className="pc-eyebrow">Related incidents</p><div className="pc-related">{state.incidents.filter(i => i.deviceIds.includes(device.id)).map(i => <button key={i.id} onClick={() => { select(i.id); navigate('incidents') }}><ShieldAlert size={14} /><span>{i.title}</span><ArrowUpRight size={13} /></button>)}{!state.incidents.some(i => i.deviceIds.includes(device.id)) && <p className="pc-muted">No incidents linked to this entity.</p>}</div>
    <div className="pc-inspector-actions"><button className="pc-button" onClick={() => navigate('twin')}><Box size={14} /> Locate in twin</button><button className="pc-button" onClick={() => navigate('network')}><Network size={14} /> Network details</button></div>
    <p className="pc-eyebrow pc-muted">Synthetic entity · Agent context synchronized</p>
  </motion.aside>}{incident && workspace !== 'incidents' && <motion.button className="pc-incident-toast" initial={{ y: 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} onClick={() => navigate('incidents')}><ShieldAlert size={18} /><span><b>{incident.title}</b><small>Open evidence & investigation history</small></span><ArrowUpRight size={16} /></motion.button>}</AnimatePresence>
}
