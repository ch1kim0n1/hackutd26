import { lazy, Suspense, useState } from 'react'
import { Bot, Check, Play, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAgentProvider } from '@/lib/agents/context'
import { agentContext } from '@/mock/security'
import { usePhantomStore } from '@/store/use-phantom-store'

const CopilotExample = lazy(() => import('./CopilotExample'))
export default function IntelligenceExample() {
  const provider = useAgentProvider()
  const status = usePhantomStore(state => state.status)
  const findings = usePhantomStore(state => state.findings)
  const approvals = usePhantomStore(state => state.approvals)
  const events = usePhantomStore(state => state.events)
  const [reason, setReason] = useState('Review fixture inspection proposal')
  const [error, setError] = useState('')
  const [chat, setChat] = useState(false)
  const pending = approvals.find(approval => approval.status === 'pending')
  async function run() {
    setError('')
    try { await provider.investigate({ id: `task-${events.length + 1}`, title: 'Correlate Lab A fixtures', context: agentContext }) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Investigation failed') }
  }
  async function decide(decision: 'approved' | 'rejected') {
    if (!pending) return
    try { await provider.decide(pending.id, decision, 'demo-operator', reason); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Decision failed') }
  }
  return <div className="space-y-6">
    <div className="example-toolbar"><div className="flex items-center gap-3"><Bot className="text-primary" /><Badge variant="outline" role="status">{status.replaceAll('_', ' ')}</Badge></div><Button onClick={run} disabled={status === 'investigating' || !!pending}><Play />Run mock investigation</Button></div>
    <p className="note">Background events feed shared state across components. Fixed context: {agentContext.incidentId}. Provider: {provider.mode}.</p>
    {findings.map(finding => <div key={finding.id} className="rounded-lg border p-4 space-y-2"><p className="text-sm">{finding.summary}</p><p className="note">Fixture confidence: {Math.round(finding.confidence * 100)}% · {finding.evidenceIds.join(', ')}</p><p className="text-sm text-[var(--phantom-warning)]">{finding.uncertainty}</p></div>)}
    {pending && <div className="rounded-lg border border-[var(--phantom-warning)] p-4 space-y-4"><div><h3 className="text-sm font-medium">Human decision required · simulation</h3><p className="note mt-2">{pending.action.description}</p></div><div className="space-y-2"><Label htmlFor="approval-reason">Decision reason</Label><Input id="approval-reason" value={reason} onChange={event => setReason(event.target.value)} /></div><div className="flex flex-wrap gap-2"><Button onClick={() => decide('approved')} disabled={!reason.trim()}><Check />Approve simulation</Button><Button variant="outline" onClick={() => decide('rejected')} disabled={!reason.trim()}><X />Reject proposal</Button></div></div>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
    <div className="rounded-lg border bg-background p-4"><p className="eyebrow mb-3">Deterministic event stream</p><ol className="space-y-2 text-xs font-mono" aria-label="Agent events">{events.length === 0 && <li className="text-muted-foreground">Awaiting a mock investigation.</li>}{events.map(event => <li key={event.id}><span className="text-muted-foreground">{event.at.slice(11, 19)} UTC</span> <span className="text-primary">{event.type}</span> {'status' in event ? event.status : event.type === 'action' ? 'simulated · no actuation' : event.type === 'approval' ? event.approval.status : 'fixture correlation'}</li>)}</ol></div>
    <div className="border-t pt-5 space-y-4"><Button variant="outline" onClick={() => setChat(value => !value)}>{chat ? 'Hide' : 'Open'} optional CopilotKit conversation</Button>{chat && <Suspense fallback={<p className="note">Loading local CopilotKit integration…</p>}><CopilotExample /></Suspense>}</div>
  </div>
}
