import { Navigate, useSearchParams } from 'react-router-dom'

/** Redirect legacy route → tab interno Pattern Lab. */
export function CecchinoLabPatternLabPage() {
  const [params] = useSearchParams()
  const runIds = params.get('run_ids')
  const qs = new URLSearchParams()
  qs.set('tab', 'pattern_lab')
  if (runIds) qs.set('run_ids', runIds)
  return <Navigate to={`/cecchino-lab?${qs.toString()}`} replace />
}
