import React, { lazy, Suspense, useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import './styles/index.css'

const App = lazy(() => import('./App'))
const Landing = lazy(() => import('./landing/Landing'))
// `/` with no workspace hash and no query (e.g. ?live=fixture) shows the landing page.
const isLanding = () => !window.location.hash && !window.location.search

function Root() {
  const [landing, setLanding] = useState(isLanding)
  useEffect(() => {
    const sync = () => { setLanding(isLanding()); if (isLanding()) window.scrollTo(0, 0) }
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  return <Suspense fallback={null}>{landing ? <Landing /> : <App />}</Suspense>
}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Root /></React.StrictMode>)
