import { useCallback, useState } from 'react'
import {
  postGoalIntensityV5Audit,
  type GoalIntensityV5AuditResponse,
} from '../lib/cecchinoGoalIntensityV5ResearchApi'
import { formatFetchError } from '../utils/formatFetchError'

type SharedFilters = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

export function useCecchinoGoalIntensityV5Audit(filters: SharedFilters) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [audit, setAudit] = useState<GoalIntensityV5AuditResponse | null>(null)

  const runAudit = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const compId = filters.competitionId.trim() ? Number(filters.competitionId) : null
      const result = await postGoalIntensityV5Audit({
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        competition_id: compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
      })
      setAudit(result)
    } catch (err) {
      setError(formatFetchError(err))
      setAudit(null)
    } finally {
      setLoading(false)
    }
  }, [filters.competitionId, filters.dateFrom, filters.dateTo])

  return { loading, error, audit, runAudit }
}
