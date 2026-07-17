import { useCallback, useState } from 'react'
import {
  postGoalIntensityV5CandidateIndices,
  type GoalIntensityV5CandidateIndicesResponse,
} from '../lib/cecchinoGoalIntensityV5ResearchApi'
import { formatFetchError } from '../utils/formatFetchError'

type SharedFilters = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

export function useCecchinoGoalIntensityV5CandidateIndices(filters: SharedFilters) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [indices, setIndices] = useState<GoalIntensityV5CandidateIndicesResponse | null>(null)

  const runCandidateIndices = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const compId = filters.competitionId.trim() ? Number(filters.competitionId) : null
      const result = await postGoalIntensityV5CandidateIndices({
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        competition_id: compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
      })
      setIndices(result)
    } catch (err) {
      setError(formatFetchError(err))
      setIndices(null)
    } finally {
      setLoading(false)
    }
  }, [filters.competitionId, filters.dateFrom, filters.dateTo])

  return { loading, error, indices, runCandidateIndices }
}
