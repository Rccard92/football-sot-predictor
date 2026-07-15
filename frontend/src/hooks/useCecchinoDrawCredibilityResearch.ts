import { useCallback, useState } from 'react'
import {
  postDrawCredibilityAudit,
  type DrawCredibilityAuditResponse,
} from '../lib/cecchinoDrawCredibilityResearchApi'
import { formatFetchError } from '../utils/formatFetchError'

type SharedFilters = {
  dateFrom: string
  dateTo: string
  competitionId: string
}

export function useCecchinoDrawCredibilityResearch(filters: SharedFilters) {
  const [onlyEligible, setOnlyEligible] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [audit, setAudit] = useState<DrawCredibilityAuditResponse | null>(null)

  const runAudit = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const compId = filters.competitionId.trim() ? Number(filters.competitionId) : null
      const result = await postDrawCredibilityAudit({
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        competition_id: compId != null && Number.isFinite(compId) && compId > 0 ? compId : null,
        only_eligible: onlyEligible,
      })
      setAudit(result)
    } catch (err) {
      setError(formatFetchError(err))
      setAudit(null)
    } finally {
      setLoading(false)
    }
  }, [filters.competitionId, filters.dateFrom, filters.dateTo, onlyEligible])

  return {
    onlyEligible,
    loading,
    error,
    audit,
    setOnlyEligible,
    runAudit,
  }
}
