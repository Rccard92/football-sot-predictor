import { useEffect, useMemo, useState } from 'react'
import { fetchHistoricalReliabilityCached } from '../lib/historicalReliabilityCache'
import type { HistoricalReliabilityItem } from '../lib/cecchinoKpiSignalsApi'
import { mapHistoricalReliabilityForFixture } from '../lib/historicalReliabilityUtils'

type Params = {
  scanDate: string | null | undefined
  competitionId: number | null | undefined
  todayFixtureId: number | null | undefined
  enabled: boolean
}

export function useHistoricalReliabilityForFixture({
  scanDate,
  competitionId,
  todayFixtureId,
  enabled,
}: Params) {
  const [hrItemsFull, setHrItemsFull] = useState<Record<string, HistoricalReliabilityItem>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled || !scanDate) {
      setHrItemsFull({})
      setLoading(false)
      setError(null)
      return
    }
    let cancelled = false
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetchHistoricalReliabilityCached({
          date_from: scanDate,
          date_to: scanDate,
          competition_id: competitionId ?? null,
        })
        if (cancelled) return
        setHrItemsFull(res.items || {})
      } catch {
        if (cancelled) return
        setHrItemsFull({})
        setError('Affidabilità non disponibile')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [enabled, scanDate, competitionId])

  const byMarketKey = useMemo(
    () =>
      enabled && scanDate
        ? mapHistoricalReliabilityForFixture(hrItemsFull, todayFixtureId)
        : {},
    [enabled, scanDate, hrItemsFull, todayFixtureId],
  )

  return {
    byMarketKey,
    loading,
    error,
  }
}
