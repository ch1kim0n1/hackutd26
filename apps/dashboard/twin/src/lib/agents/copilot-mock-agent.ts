import { AbstractAgent } from '@ag-ui/client'
import { EventType, type BaseEvent, type RunAgentInput } from '@ag-ui/core'
import { from, type Observable } from 'rxjs'

/** An actual AG-UI transport for CopilotKit, with a fixed response and no HTTP calls. */
export class CopilotMockAgent extends AbstractAgent {
  run(input: RunAgentInput): Observable<BaseEvent> {
    const messageId = `fixture-${input.runId}`
    return from([
      { type: EventType.RUN_STARTED, threadId: input.threadId, runId: input.runId },
      { type: EventType.TEXT_MESSAGE_START, messageId, role: 'assistant' },
      { type: EventType.TEXT_MESSAGE_CONTENT, messageId, delta: 'Local fixture response: cabinet contact and an unknown AP share Lab A. Exposure is unverified. Use the investigation example to review a simulated inspection proposal. No model or actuator is connected.' },
      { type: EventType.TEXT_MESSAGE_END, messageId },
      { type: EventType.RUN_FINISHED, threadId: input.threadId, runId: input.runId },
    ] as BaseEvent[])
  }
}
