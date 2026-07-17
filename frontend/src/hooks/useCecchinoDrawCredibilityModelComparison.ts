import { useCallback, useRef, useState } from 'react'
import {
  postDrawCredibilityModelComparison,
  type DrawCredibilityModelComparisonResponse,
} from '../lib/cecchinoDrawCredibilityResearchApi'
import { formatFetchError } from '../utils/formatFetchError'

type SharedFilters = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

export function useCecchinoDrawCredibilityModelComparison(shared: SharedFilters) {
  const [finalHoldoutPct, setFinalHoldoutPct] = useState(0.25)
  const [innerSplits, setInnerSplits] = useState(3)
  const [bootstrapIterations, setBootstrapIterations] = useState(500)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastAnalysis, setLastAnalysis] = useState<DrawCredibilityModelComparisonResponse | null>(
    null,
  )
  const [lastExecutedAt, setLastExecutedAt] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const parseCompetitionId = useCallback(() => {
    const compId = shared.competitionId.trim() ? Number(shared.competitionId) : null
    return compId != null && Number.isFinite(compId) && compId > 0 ? compId : null
  }, [shared.competitionId])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setLastAnalysis(null)
    setLastExecutedAt(null)
    setError(null)
  }, [])

  const runComparison = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setError(null)
    try {
      const result = await postDrawCredibilityModelComparison(
        {
          date_from: shared.dateFrom,
          date_to: shared.dateTo,
          competition_id: parseCompetitionId(),
          final_holdout_pct: finalHoldoutPct,
          inner_splits: innerSplits,
          bootstrap_iterations: bootstrapIterations,
        },
        { signal: controller.signal },
      )
      setLastAnalysis(result)
      setLastExecutedAt(new Date().toISOString())
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setError(formatFetchError(err))
      setLastAnalysis(null)
      setLastExecutedAt(null)
    } finally {
      if (abortRef.current === controller) {
        setLoading(false)
        abortRef.current = null
      }
    }
  }, [
    bootstrapIterations,
    finalHoldoutPct,
    innerSplits,
    parseCompetitionId,
    shared.dateFrom,
    shared.dateTo,
  ])

  return {
    finalHoldoutPct,
    innerSplits,
    bootstrapIterations,
    loading,
    error,
    lastAnalysis,
    lastExecutedAt,
    setFinalHoldoutPct,
    setInnerSplits,
    setBootstrapIterations,
    runComparison,
    reset,
  }
}
