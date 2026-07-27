import { useEffect, useState } from 'react'
import {
  getCecchinoLabAnalyticsOverview,
  type CecchinoLabAnalyticsFilters,
  type CecchinoLabAnalyticsOverview,
} from '../../../lib/cecchinoLabApi'

export function useAnalyticsOverview(filters: CecchinoLabAnalyticsFilters, refreshKey: number) {
  const [data, setData] = useState<CecchinoLabAnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getCecchinoLabAnalyticsOverview(filters)
      .then((res) => {
        if (!cancelled) {
          setData(res)
          setError(null)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Errore analytics')
          setData(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [filters.season_label, filters.country, filters.competition, filters.dataset_id, refreshKey])

  return { data, loading, error }
}
