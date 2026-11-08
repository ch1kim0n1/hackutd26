import { useState } from 'react'
import { CopilotKit, useCopilotAction, useCopilotReadable } from '@copilotkit/react-core'
import { CopilotChat } from '@copilotkit/react-ui'
import { AbstractAgent } from '@ag-ui/client'
import { EventType, type BaseEvent, type RunAgentInput } from '@ag-ui/core'
import { from, type Observable } from 'rxjs'
import { useCommandStore } from '../store'
import { contextBrief } from '../context-brief'
import '@copilotkit/react-ui/styles.css'

class CommandContextAgent extends AbstractAgent {
  run(input: RunAgentInput): Observable<BaseEvent> {
    const { state, selectedId } = useCommandStore.getState()
    const last = input.messages.filter(m => m.role === 'user').at(-1)
    const query = typeof last?.content === 'string' ? last.content : ''
    const messageId = `context-${input.runId}`
    return from([
      { type: EventType.RUN_STARTED, threadId: input.threadId, runId: input.runId },
      { type: EventType.TEXT_MESSAGE_START, messageId, role: 'assistant' },
      { type: EventType.TEXT_MESSAGE_CONTENT, messageId, delta: contextBrief(state, selectedId, query) },
      { type: EventType.TEXT_MESSAGE_END, messageId },
      { type: EventType.RUN_FINISHED, threadId: input.threadId, runId: input.runId },
    ] as BaseEvent[])
  }
}
function ContextBridge() {
  const { state, selectedId, select, navigate } = useCommandStore()
  useCopilotReadable({ description: 'Phantom Command synthetic operational context. Observations and findings are separate; no hardware or inference is connected.', value: { provenance: 'DEMO', selectedId, simulation: state.simulation, elapsed: state.elapsed, incidents: state.incidents, findings: state.findings, rover: state.rover, approvals: state.approvals } })
  useCopilotAction({ name: 'select_demo_entity', description: 'Focus an existing synthetic device or incident in the interface. Read-only navigation, no actuation.', parameters: [{name:'entityId',type:'string',required:true}], handler: ({entityId}) => { const current = useCommandStore.getState().state; const device = current.devices.some(d => d.id === entityId); const incident = current.incidents.some(i => i.id === entityId); if (!device && !incident) throw new Error('Unknown demo entity'); select(entityId); navigate(device ? 'twin' : 'incidents'); return 'Shared selection updated.' } }, [select,navigate])
  return <p className="pc-context-boundary"><span className="pc-dot pc-purple" /> Context synchronized · {selectedId ?? 'Entire facility'}</p>
}
export default function ContextConversation() {
  const [agents] = useState(() => ({ default: new CommandContextAgent({agentId:'default',description:'Read-only deterministic Phantom Command context'}) }))
  return <CopilotKit agents__unsafe_dev_only={agents} showDevConsole={false} enableInspector={false}><div className="pc-context-conversation"><ContextBridge /><CopilotChat suggestions={[]} labels={{title:'Operational context',initial:'This optional console reads the same records as every workspace. Request the current context or rover status; investigations run automatically in the background.',placeholder:'Current context or rover status…'}} /></div></CopilotKit>
}
