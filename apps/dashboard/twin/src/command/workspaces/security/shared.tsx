import { useEffect, useRef, type ReactNode } from 'react'
import { init, use as registerCharts, type ECharts } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Check, ShieldCheck, X } from 'lucide-react'
import { palette } from '@/styles/palette'
import { useCommandStore } from '../../store'
import { formatTime, type Approval, type Device } from '../../model'

registerCharts([LineChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer])

export function Metric({ label, value, detail, icon, tone = 'cyan' }: { label: string; value: ReactNode; detail: string; icon: ReactNode; tone?: string }) {
  return <div className={`sec-metric sec-tone-${tone}`}><div className="sec-metric-label">{label}{icon}</div><strong>{value}</strong><span>{detail}</span></div>
}

export function Status({ value }: { value: string }) {
  return <span className={`sec-status sec-status-${value}`}><i />{value.replaceAll('_', ' ')}</span>
}

export function Empty({ icon, title, detail }: { icon?: ReactNode; title: string; detail: string }) {
  return <div className="sec-empty">{icon ?? <ShieldCheck size={24} />}<strong>{title}</strong><p>{detail}</p></div>
}

export function ApprovalCard({ approval }: { approval: Approval }) {
  const decide = useCommandStore(store => store.decideApproval)
  const devices = useCommandStore(store => store.state.devices)
  const device = devices.find(item => item.id === approval.targetId)
  return <div className="sec-approval"><div className="sec-row"><span className="pc-eyebrow">Human authorization</span><Status value={approval.status} /></div><strong>Simulate device isolation</strong><p>{device?.name ?? approval.targetId} · {approval.reason}</p>{approval.status === 'pending' ? <div className="sec-actions"><button className="pc-button sec-approve" onClick={() => decide(approval.id, true)}><Check size={13} />Approve simulation</button><button className="pc-button" onClick={() => decide(approval.id, false)}><X size={13} />Reject</button></div> : <small>Operator decision recorded at {formatTime(approval.decidedAt ?? approval.at)} UTC. Simulation only.</small>}</div>
}

export function SignalChart({ device }: { device: Device }) {
  const element = useRef<HTMLDivElement>(null)
  const chart = useRef<ECharts | null>(null)
  useEffect(() => {
    if (!element.current) return
    chart.current = init(element.current)
    const observer = new ResizeObserver(() => chart.current?.resize())
    observer.observe(element.current)
    return () => { observer.disconnect(); chart.current?.dispose(); chart.current = null }
  }, [])
  useEffect(() => {
    const radio = device.protocol === 'Wi-Fi' || device.protocol === 'BLE'
    chart.current?.setOption({
      animation: false, backgroundColor: 'transparent',
      aria: { enabled: true, label: { description: `Simulated signal history for ${device.name}: ${device.signalHistory.join(', ')} dBm.` } },
      grid: { left: 42, right: 14, top: 20, bottom: 28 },
      tooltip: { trigger: 'axis', renderMode: 'richText', backgroundColor: palette.panel, textStyle: { color: palette.text, fontSize: 11 }, borderColor: '#423e3b' },
      xAxis: { type: 'category', boundaryGap: false, data: device.signalHistory.map((_, index) => `${index * 2}s`), axisLabel: { color: palette.muted, fontSize: 9, interval: Math.max(0, Math.floor(device.signalHistory.length / 4)) }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#35332f' } } },
      yAxis: { type: 'value', min: -100, max: -20, axisLabel: { color: palette.muted, fontSize: 9 }, splitLine: { lineStyle: { color: '#2a2825', type: 'dashed' } } },
      series: [{ name: radio ? 'Signal strength · dBm' : 'Monitoring signal · dBm', type: 'line', smooth: 0.3, showSymbol: false, data: device.signalHistory, lineStyle: { width: 2, color: device.status === 'threat' ? palette.threat : palette.wall }, areaStyle: { opacity: 0.06, color: palette.wall } }],
    }, true)
  }, [device])
  return <div ref={element} className="sec-signal-chart" role="img" aria-label={`Simulated signal history for ${device.name}`} />
}
