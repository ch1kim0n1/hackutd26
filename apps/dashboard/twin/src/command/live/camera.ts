/** The camera service has no authentication: require an explicit SSH tunnel. */
export function localCameraBase(raw: string): string | null {
  try {
    const url = new URL(raw)
    if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) return null
    return url.origin
  } catch { return null }
}
