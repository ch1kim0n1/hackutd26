import { useEffect, useRef, useState } from 'react'
import { init, use as registerCharts } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Button } from '@/components/ui/button'
import { telemetryOption } from '@/lib/charts/telemetry-option'
import { telemetry } from '@/mock/security'

registerCharts([LineChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer])
export default function TelemetryExample() {
  const element = useRef<HTMLDivElement>(null)
  const [metric, setMetric] = useState<'packets' | 'latency'>('packets')
  useEffect(() => {
    if (!element.current) return
    const chart = init(element.current)
    chart.setOption(telemetryOption(metric))
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(element.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [metric])
  return <div className="space-y-4">
    <div className="flex gap-2"><Button variant={metric === 'packets' ? 'default' : 'outline'} onClick={() => setMetric('packets')}>Packet rate</Button><Button variant={metric === 'latency' ? 'default' : 'outline'} onClick={() => setMetric('latency')}>Latency</Button></div>
    <div ref={element} className="h-[360px] w-full" data-testid="telemetry-chart" role="img" aria-label={`Synthetic ${metric} telemetry, eight fixed samples at 18:00-18:07 UTC`} />
    <details className="note"><summary className="cursor-pointer">Accessible sample values</summary><p className="mt-2">{telemetry.time.map((time, i) => `${time}: ${telemetry[metric][i]}`).join(' · ')}</p></details>
    <p className="note">Apache ECharts · fixed samples · 07 Nov 2026, UTC. Hover for values. No timer, telemetry service, or live network collection.</p>
  </div>
}
