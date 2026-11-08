import type { EChartsCoreOption } from 'echarts/core'
import { palette } from '@/styles/palette'
import { telemetry } from '@/mock/security'

export function telemetryOption(metric: 'packets' | 'latency'): EChartsCoreOption {
  return {
    animation: false, backgroundColor: 'transparent',
    aria: { enabled: true, label: { description: `Synthetic ${metric} telemetry. Eight fixed samples at 18:00 to 18:07 UTC on 7 November 2026. Values: ${telemetry[metric].join(', ')}.` } },
    color: [metric === 'packets' ? palette.wall : palette.infrastructure],
    tooltip: { trigger: 'axis', renderMode: 'richText' },
    grid: { left: 55, right: 20, top: 35, bottom: 45 },
    xAxis: { type: 'category', data: telemetry.time, axisLabel: { color: palette.muted }, axisLine: { lineStyle: { color: palette.muted } } },
    yAxis: { type: 'value', name: metric === 'packets' ? 'packets/s' : 'ms', nameTextStyle: { color: palette.muted }, axisLabel: { color: palette.muted }, splitLine: { lineStyle: { color: palette.panel } } },
    series: [{ name: metric === 'packets' ? 'Packet rate' : 'Latency', type: 'line', data: telemetry[metric], symbolSize: 7, lineStyle: { width: 2 }, areaStyle: { opacity: 0.06 } }],
  }
}
