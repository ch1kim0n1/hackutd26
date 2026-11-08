import type { StoreApi } from 'zustand'
import { WORKSPACES, type CommandStore, type Workspace } from './model'

/** Keep all navigation sources and browser history on the same workspace. */
export function connectWorkspaceHistory(store: StoreApi<CommandStore>, browser: Window) {
  let fromLocation = false
  const readLocation = () => {
    const requested = browser.location.hash.slice(1)
    const workspace = WORKSPACES.includes(requested as Workspace) ? requested as Workspace : 'overview'
    // An empty hash is left alone: on `/` it belongs to the landing page.
    if (browser.location.hash && browser.location.hash !== `#${workspace}`) browser.history.replaceState(browser.history.state, '', `#${workspace}`)
    // Following the URL must never push a new entry, or Back to `/` would bounce straight to `#overview`.
    fromLocation = true
    try { store.getState().navigate(workspace) } finally { fromLocation = false }
  }

  readLocation()
  const unsubscribe = store.subscribe((current, previous) => {
    if (!fromLocation && current.workspace !== previous.workspace && browser.location.hash !== `#${current.workspace}`) {
      browser.history.pushState(null, '', `#${current.workspace}`)
    }
  })
  browser.addEventListener('popstate', readLocation)
  browser.addEventListener('hashchange', readLocation)
  return () => {
    unsubscribe()
    browser.removeEventListener('popstate', readLocation)
    browser.removeEventListener('hashchange', readLocation)
  }
}
