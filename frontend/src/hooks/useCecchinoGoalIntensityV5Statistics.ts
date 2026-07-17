import { useCallback, useState } from 'react'
import {
  postGoalIntensityV5Statistics,
  type GoalIntensityV5StatisticsResponse,
} from '../lib/cecchinoGoalIntensityV5ResearchApi'
import { formatFetchError } from '../utils/formatFetchError'

type SharedFilters = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

export function useCecchinoGoalIntensityV5Statistics(filters: SharedFilters) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statistics, setStatistics] = useState<GoalIntensityV5StatisticsResponse | null>(null)

  const runStatistics = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const compId = filters.competitionId.trim() ? Number(filters.competitionId) : null
      const result = await postGoalIntensityV5Statistics({
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        competition_id: compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
      })
      setStatistics(result)
    } catch (err) {
      setError(formatFetchError(err))
      setStatistics(null)
    } finally {
      setLoading(false)
    }
  }, [filters.competitionId, filters.dateFrom, filters.dateTo])

  return { loading, error, statistics, runStatistics }
}
