import { Component, type ErrorInfo, type ReactNode } from 'react'
export class ExampleBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state: { error: string | null } = { error: null }
  static getDerivedStateFromError(error: Error) { return { error: error.message } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Integration example failed', error, info) }
  render() {
    if (this.state.error) return <div role="alert" className="rounded-lg border border-destructive p-6"><p>Unable to render this integration example.</p><p className="note mt-2">{this.state.error}</p><p className="note mt-2">The spatial example requires a WebGL2 capable browser.</p></div>
    return this.props.children
  }
}
