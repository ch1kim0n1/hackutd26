import type { Edge, Node } from '@xyflow/react'
import { palette } from '@/styles/palette'

export const topologyNodes: Node[] = [
  { id: 'gateway', position: { x: 240, y: 30 }, data: { label: 'Mock gateway' }, type: 'input' },
  { id: 'rack-01', position: { x: 20, y: 190 }, data: { label: 'Compute rack 01' } },
  { id: 'sensor-01', position: { x: 240, y: 190 }, data: { label: 'Cabinet sensor · investigate' } },
  { id: 'rover-01', position: { x: 460, y: 190 }, data: { label: 'Survey rover' } },
].map(node => ({ ...node, style: { background: palette.panel, color: palette.text, borderColor: node.id === 'sensor-01' ? palette.warning : palette.wall, width: 180, fontSize: 12, padding: 16 } }))
export const topologyEdges: Edge[] = ['rack-01', 'sensor-01', 'rover-01'].map(target => ({ id: `gateway-${target}`, source: 'gateway', target, style: { stroke: palette.wall } }))
