import { useCallback } from 'react'
import { addEdge, Background, Controls, ReactFlow, useEdgesState, useNodesState, type OnConnect } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { topologyEdges, topologyNodes } from '@/lib/graphs/security-topology'
import { usePhantomStore } from '@/store/use-phantom-store'

export default function TopologyExample() {
  const [nodes, setNodes, onNodesChange] = useNodesState(topologyNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(topologyEdges)
  const select = usePhantomStore(state => state.selectDevice)
  const selected = usePhantomStore(state => state.selectedDeviceId)
  const onConnect: OnConnect = useCallback(connection => setEdges(existing => addEdge(connection, existing)), [setEdges])
  return <div className="space-y-4">
    <div className="h-[430px] overflow-hidden rounded-lg border" data-testid="topology"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => select(node.id)} fitView colorMode="dark" minZoom={0.3} maxZoom={2} attributionPosition="bottom-right"><Background gap={24} /><Controls /></ReactFlow></div>
    <div className="example-toolbar"><p className="note">Drag nodes · connect handles · use zoom controls. Changes last until this example unmounts.</p><button className="text-sm text-primary underline" onClick={() => { setNodes(topologyNodes); setEdges(topologyEdges) }}>Reset topology</button></div>
    <p className="note" role="status">Shared selection: {selected ?? 'none'}. Connections are authored fixtures, not discovered network links.</p>
  </div>
}
