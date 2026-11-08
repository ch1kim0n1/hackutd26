import { createContext, useContext, useEffect, type ReactNode } from 'react'
import type { AgentProvider } from '@/types/agent'
import { usePhantomStore } from '@/store/use-phantom-store'

const ProviderContext = createContext<AgentProvider | null>(null)
export function AgentBoundary({ provider, children }: { provider: AgentProvider; children: ReactNode }) {
  useEffect(() => provider.subscribe(usePhantomStore.getState().receive), [provider])
  return <ProviderContext.Provider value={provider}>{children}</ProviderContext.Provider>
}
export function useAgentProvider() {
  const provider = useContext(ProviderContext)
  if (!provider) throw new Error('Wrap this component in AgentBoundary')
  return provider
}
