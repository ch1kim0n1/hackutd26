import { useState } from 'react'
import { CopilotKit, useCopilotAction, useCopilotReadable } from '@copilotkit/react-core'
import { CopilotChat } from '@copilotkit/react-ui'
import '@copilotkit/react-ui/styles.css'
import { CopilotMockAgent } from '@/lib/agents/copilot-mock-agent'
import { agentContext } from '@/mock/security'
import { usePhantomStore } from '@/store/use-phantom-store'

function ContextBridge() {
  const selected = usePhantomStore(state => state.selectedDeviceId)
  const select = usePhantomStore(state => state.selectDevice)
  useCopilotReadable({ description: 'Synthetic incident context and selected fixture device', value: { ...agentContext, selectedDeviceId: selected } })
  useCopilotAction({
    name: 'select_fixture_device', description: 'Select one known synthetic fixture. No actuation.',
    parameters: [{ name: 'deviceId', type: 'string', required: true }],
    handler: ({ deviceId }) => {
      if (!['rack-01', 'rack-02', 'sensor-01', 'ap-unknown', 'rover-01'].includes(deviceId)) throw new Error('Unknown fixture')
      select(deviceId)
      return 'Fixture selection updated'
    },
  }, [select])
  return <p className="note">Readable context registered · selection tool registered · local transport. This fixture returns fixed text; it does not reason or invoke tools.</p>
}

export default function CopilotExample() {
  const [agents] = useState(() => ({ default: new CopilotMockAgent({ agentId: 'default', description: 'Deterministic local fixture' }) }))
  return <CopilotKit agents__unsafe_dev_only={agents} showDevConsole={false} enableInspector={false}>
    <div className="space-y-4"><ContextBridge />
      <div className="copilot-fixture h-[390px] overflow-hidden rounded-lg border"><CopilotChat suggestions={[]} labels={{ title: 'Local CopilotKit fixture', initial: 'Optional conversation example. Send any message to receive a deterministic local response.', placeholder: 'Ask about the fixture…' }} /></div>
      <p className="note">Nemotron inference, autonomous tool choice, persistence, authentication, and streaming from a backend are unsupported here. Replace the development transport with an authenticated runtime URL when those services exist.</p>
    </div>
  </CopilotKit>
}
