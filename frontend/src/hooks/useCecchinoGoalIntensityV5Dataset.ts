import { useCallback, useState } from 'react'
import {
  classifyGoalIntensityFetchError,
  postGoalIntensityV5Dataset,
  type GoalIntensityV5DatasetResponse,
} from '../lib/cecchinoGoalIntensityV5ResearchApi'

type SharedFilters = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

export function useCecchinoGoalIntensityV5Dataset(filters: SharedFilters) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dataset, setDataset] = useState<GoalIntensityV5DatasetResponse | null>(null)

  const runDataset = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const compId = filters.competitionId.trim() ? Number(filters.competitionId) : null
      const result = await postGoalIntensityV5Dataset({
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        competition_id: compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
      })
      setDataset(result)
    } catch (err) {
      setError(classifyGoalIntensityFetchError(err, 'summary'))
      setDataset(null)
    } finally {
      setLoading(false)
    }
  }, [filters.competitionId, filters.dateFrom, filters.dateTo])

  return { loading, error, dataset, runDataset }
}
