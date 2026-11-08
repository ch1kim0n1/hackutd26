import { lazy, Suspense, useState, type ComponentType } from 'react'
import { Activity, ArrowUpRight, Bot, Box, FlaskConical, Grid2X2, Layers, Network, Shield, Table2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarTrigger, useSidebar } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { ExampleBoundary } from '@/components/phantom/ExampleBoundary'
import { AgentBoundary } from '@/lib/agents/context'
import { MockAgentProvider } from '@/lib/agents/mock-provider'
import { usePhantomStore } from '@/store/use-phantom-store'

const examples = [
  { id: 'components', name: 'Component gallery', title: 'Interface foundations', subtitle: 'Editable components, accessible controls, and a shared visual language.', kit: 'shadcn/ui · Tailwind · Zustand', icon: Layers, component: lazy(() => import('@/examples/ComponentGallery')) },
  { id: 'spatial', name: 'Digital twin', title: 'Spatial rendering', subtitle: 'Primitive geometry in a consistent world frame. Built for tactical schematics.', kit: 'Three.js · Fiber · Drei · Postprocessing', icon: Box, component: lazy(() => import('@/examples/DigitalTwinExample')) },
  { id: 'tables', name: 'Security tables', title: 'Structured device records', subtitle: 'Sortable, searchable inventory with shared object selection.', kit: 'AG Grid Community · Zustand', icon: Table2, component: lazy(() => import('@/examples/SecurityTableExample')) },
  { id: 'topology', name: 'Network topology', title: 'Connected systems', subtitle: 'An editable graph of authored device relationships.', kit: 'React Flow', icon: Network, component: lazy(() => import('@/examples/TopologyExample')) },
  { id: 'telemetry', name: 'Telemetry', title: 'Signal over time', subtitle: 'A small deterministic series with reusable chart configuration.', kit: 'Apache ECharts', icon: Activity, component: lazy(() => import('@/examples/TelemetryExample')) },
  { id: 'layout', name: 'Panel layout', title: 'Composable workspace', subtitle: 'Move and resize isolated panels to validate the layout engine.', kit: 'React Grid Layout', icon: Grid2X2, component: lazy(() => import('@/examples/LayoutExample')) },
  { id: 'intelligence', name: 'Agent integration', title: 'Intelligence across the interface', subtitle: 'Structured findings, background events, and explicit human decisions.', kit: 'Mock AgentProvider · CopilotKit', icon: Bot, component: lazy(() => import('@/examples/IntelligenceExample')) },
] as const

function Navigation({ active, onSelect }: { active: string; onSelect: (id: string) => void }) {
  const { isMobile, setOpenMobile } = useSidebar()
  return <Sidebar collapsible="offcanvas">
    <SidebarHeader className="p-5"><div className="flex items-center gap-3"><div className="brand-mark"><Shield size={21} /></div><div><p className="brand-name">PHANTOM</p><p className="eyebrow mt-1">Command / UI foundation</p></div></div></SidebarHeader>
    <SidebarContent><SidebarGroup><SidebarGroupLabel>Integration examples</SidebarGroupLabel><SidebarMenu>{examples.map((example, i) => <SidebarMenuItem key={example.id}><SidebarMenuButton isActive={active === example.id} onClick={() => { onSelect(example.id); if (isMobile) setOpenMobile(false) }} className="h-11 px-3" aria-current={active === example.id ? 'page' : undefined}><example.icon /><span>{example.name}</span><span className="ml-auto font-mono text-[10px] text-muted-foreground">0{i + 1}</span></SidebarMenuButton></SidebarMenuItem>)}</SidebarMenu></SidebarGroup></SidebarContent>
    <SidebarFooter className="p-5"><div className="rounded-lg border p-3"><FlaskConical size={16} className="mb-2 text-[var(--phantom-warning)]" /><p className="text-xs font-medium">Acquisition & preparation</p><p className="note mt-2">Static fixtures. Local interactions. Ready for the application team.</p></div><Button asChild variant="ghost" className="mt-2 justify-between text-xs"><a href="/legacy.html">Original twin demo<ArrowUpRight /></a></Button></SidebarFooter>
  </Sidebar>
}

export default function App() {
  const [active, setActive] = useState(() => examples.some(example => example.id === location.hash.slice(1)) ? location.hash.slice(1) : 'components')
  const [provider] = useState(() => new MockAgentProvider())
  const selected = usePhantomStore(state => state.selectedDeviceId)
  const status = usePhantomStore(state => state.status)
  const example = examples.find(example => example.id === active) ?? examples[0]
  const Example: ComponentType = example.component
  function navigate(id: string) { setActive(id); history.replaceState(null, '', `#${id}`) }
  return <TooltipProvider><AgentBoundary provider={provider}><SidebarProvider><Navigation active={active} onSelect={navigate} /><SidebarInset>
    <header className="lab-header"><div className="flex items-center gap-3"><SidebarTrigger /><span className="eyebrow">Development lab</span></div><div className="flex items-center gap-2"><span className="hidden text-xs text-muted-foreground sm:inline">Local fixtures only</span><Badge variant="outline" className="text-[var(--phantom-warning)]">SYNTHETIC</Badge></div></header>
    <div className="lab-main"><div className="example-heading"><p className="eyebrow text-primary">Phantom Command <span className="px-2 text-muted-foreground">/</span> {example.name}</p><h1>{example.title}</h1><p className="text-sm leading-6 text-muted-foreground">{example.subtitle}</p><div className="mt-4 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"><span className="status-dot" />{example.kit}</div></div>
      <section className="example-surface" aria-label={example.name}><ExampleBoundary key={active}><Suspense fallback={<p className="note p-6">Loading integration example…</p>}><Example /></Suspense></ExampleBoundary></section>
      <footer className="lab-footer"><span>Foundation v0.1 · React + TypeScript + Vite</span><span role="status">Selection: {selected ?? 'none'} · Agent: {status.replaceAll('_', ' ')}</span></footer>
    </div>
  </SidebarInset></SidebarProvider><Toaster theme="dark" /></AgentBoundary></TooltipProvider>
}
