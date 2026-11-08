import { useState, type RefObject } from 'react'
import GridLayout, { useContainerWidth, type Layout } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import { GripHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'

const initial: Layout = [
  { i: 'a', x: 0, y: 0, w: 3, h: 3, minW: 2, minH: 2 },
  { i: 'b', x: 3, y: 0, w: 3, h: 3, minW: 2, minH: 2 },
  { i: 'c', x: 0, y: 3, w: 6, h: 2, minW: 2, minH: 2 },
]
export default function LayoutExample() {
  const { width, containerRef, mounted } = useContainerWidth()
  // RGL's React 19 style declaration nests null; React 18 RefObject already includes null.
  const [layout, setLayout] = useState<Layout>(initial)
  const [changes, setChanges] = useState(0)
  return <div className="space-y-4">
    <div className="example-toolbar"><p className="note">Drag a panel header or resize its lower-right corner.</p><Button variant="outline" onClick={() => { setLayout(initial); setChanges(0) }}>Reset layout</Button></div>
    <div ref={containerRef as RefObject<HTMLDivElement>} data-testid="layout-grid" className="min-h-[350px] rounded-lg border bg-background">
      {mounted && <GridLayout width={width} layout={layout} gridConfig={{ cols: 6, rowHeight: 56, margin: [12, 12] }} dragConfig={{ handle: '.panel-handle' }} onLayoutChange={setLayout} onDragStop={() => setChanges(count => count + 1)} onResizeStop={() => setChanges(count => count + 1)}>
        {['a', 'b', 'c'].map((key, i) => <div key={key} className="lab-panel"><div className="panel-handle"><GripHorizontal size={15} />Panel {String(i + 1).padStart(2, '0')}</div><p className="p-4 text-sm text-muted-foreground">Reusable layout slot<br /><span className="text-xs">No operational data</span></p></div>)}
      </GridLayout>}
    </div>
    <p role="status" className="note">Layout interactions: {changes}. Local example state; no layout is saved.</p>
  </div>
}
