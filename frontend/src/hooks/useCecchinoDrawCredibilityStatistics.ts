import { useCallback, useRef, useState } from 'react'
import {
  postDrawCredibilityStatisticalAnalysis,
  type DrawCredibilityStatisticsResponse,
} from '../lib/cecchinoDrawCredibilityResearchApi'
import { formatFetchError } from '../utils/formatFetchError'

type SharedFilters = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

export function useCecchinoDrawCredibilityStatistics(shared: SharedFilters) {
  const [binCount, setBinCount] = useState(5)
  const [minGroupSize, setMinGroupSize] = useState(20)
  const [bootstrapIterations, setBootstrapIterations] = useState(500)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastAnalysis, setLastAnalysis] = useState<DrawCredibilityStatisticsResponse | null>(null)
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

  const runAnalysis = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setError(null)
    try {
      const result = await postDrawCredibilityStatisticalAnalysis(
        {
          date_from: shared.dateFrom,
          date_to: shared.dateTo,
          competition_id: parseCompetitionId(),
          bin_count: binCount,
          min_group_size: minGroupSize,
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
    binCount,
    bootstrapIterations,
    minGroupSize,
    parseCompetitionId,
    shared.dateFrom,
    shared.dateTo,
  ])

  return {
    binCount,
    minGroupSize,
    bootstrapIterations,
    loading,
    error,
    lastAnalysis,
    lastExecutedAt,
    setBinCount,
    setMinGroupSize,
    setBootstrapIterations,
    runAnalysis,
    reset,
  }
}
