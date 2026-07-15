import { useCallback, useState } from 'react'
import {
  postDrawCredibilityAudit,
  type DrawCredibilityAuditResponse,
} from '../lib/cecchinoDrawCredibilityResearchApi'
import { isoDaysAgoLocal, todayLocalIso } from '../utils/dateLocal'
import { formatFetchError } from '../utils/formatFetchError'

export function useCecchinoDrawCredibilityResearch() {
  const [dateFrom, setDateFrom] = useState(() => isoDaysAgoLocal(90))
  const [dateTo, setDateTo] = useState(() => todayLocalIso())
  const [competitionId, setCompetitionId] = useState('')
  const [onlyEligible, setOnlyEligible] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [audit, setAudit] = useState<DrawCredibilityAuditResponse | null>(null)

  const runAudit = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const compId = competitionId.trim() ? Number(competitionId) : null
      const result = await postDrawCredibilityAudit({
        date_from: dateFrom,
        date_to: dateTo,
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
  }, [competitionId, dateFrom, dateTo, onlyEligible])

  return {
    dateFrom,
    dateTo,
    competitionId,
    onlyEligible,
    loading,
    error,
    audit,
    setDateFrom,
    setDateTo,
    setCompetitionId,
    setOnlyEligible,
    runAudit,
  }
}
