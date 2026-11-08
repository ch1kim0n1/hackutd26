import { useEffect, useRef } from 'react'
import { init, use as registerCharts, type EChartsType } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useReducedMotion } from 'motion/react'
import type { TelemetrySample } from '../model'
import { formatTime } from '../model'

registerCharts([LineChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer])
export default function TelemetryChart({ samples, metric = 'traffic' }: { samples: TelemetrySample[]; metric?: 'traffic' | 'latency' | 'cpu' }) {
  const ref = useRef<HTMLDivElement>(null), chart = useRef<EChartsType>()
  const reduced = useReducedMotion()
  useEffect(() => {
    if (!ref.current) return
    chart.current = init(ref.current)
    const observer = new ResizeObserver(() => chart.current?.resize())
    observer.observe(ref.current)
    return () => { observer.disconnect(); chart.current?.dispose() }
  }, [])
  useEffect(() => {
    chart.current?.setOption({ animation: !reduced, animationDurationUpdate: 400, grid: { top: 12, left: 44, right: 15, bottom: 25 }, aria: { enabled: true }, tooltip: { trigger: 'axis', backgroundColor: '#142338', borderColor: '#2c4059', textStyle: { color: '#E3F2FE', fontFamily: 'monospace', fontSize: 11 } }, xAxis: { type: 'category', boundaryGap: false, data: samples.map(s => formatTime(s.at).slice(3)), axisLabel: { color: '#8299B5', fontFamily: 'monospace', fontSize: 9, hideOverlap: true }, axisLine: { lineStyle: { color: '#203146' } }, axisTick: { show: false } }, yAxis: { type: 'value', splitNumber: 3, axisLabel: { color: '#8299B5', fontFamily: 'monospace', fontSize: 9 }, splitLine: { lineStyle: { color: '#1a2b3f', type: 'dashed' } } }, series: [{ data: samples.map(s => s[metric]), type: 'line', smooth: .25, symbol: 'none', lineStyle: { width: 2, color: '#36CFF4' }, areaStyle: { color: '#36CFF4', opacity: .07 } }] })
  }, [samples, metric, reduced])
  return <div ref={ref} className="pc-chart" role="img" aria-label={`Simulated ${metric} history. Latest value ${samples.at(-1)?.[metric] ?? 0}`} />
}
