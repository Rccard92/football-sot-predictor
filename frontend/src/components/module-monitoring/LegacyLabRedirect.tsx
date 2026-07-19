import { Navigate, useLocation } from 'react-router-dom'

type Props = {
  module: string
  view: string
}

/** Redirect legacy lab URL → workspace, preservando date_from/date_to quando presenti. */
export function LegacyLabRedirect({ module, view }: Props) {
  const location = useLocation()
  const incoming = new URLSearchParams(location.search)
  const next = new URLSearchParams()
  next.set('module', module)
  next.set('view', view)
  for (const key of ['date_from', 'date_to', 'competition_id', 'market_key']) {
    const v = incoming.get(key)
    if (v) next.set(key, v)
  }
  return <Navigate to={`/monitoraggio-moduli?${next.toString()}`} replace />
}
