import { useCallback, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  backfillKpiSignals,
  buildKpiSignalsExportUrl,
  getKpiSignalsActivations,
  getKpiSignalsSummary,
  revaluateKpiSignals,
  type KpiSignalActivationRow,
  type KpiSignalsFilters,
  type KpiSignalsSummaryResponse,
} from '../lib/cecchinoKpiSignalsApi'
import { todayIso } from '../components/cecchino-lab/signalsLabUtils'
import { formatFetchError } from '../utils/formatFetchError'
import { AdminHttpError } from '../lib/api'

export function useCecchinoKpiSignals() {
  const [dateFrom, setDateFrom] = useState(todayIso())
  const [dateTo, setDateTo] = useState(todayIso())
  const [ratingBucket, setRatingBucket] = useState('')
  const [selectionKey, setSelectionKey] = useState('')
  const [normalizedMarket, setNormalizedMarket] = useState('')
  const [evaluationStatus, setEvaluationStatus] = useState('')
  const [countryName, setCountryName] = useState('')
  const [leagueName, setLeagueName] = useState('')
  const [summary, setSummary] = useState<KpiSignalsSummaryResponse | null>(null)
  const [activations, setActivations] = useState<KpiSignalActivationRow[]>([])
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)

  const filters: KpiSignalsFilters = useMemo(
    () => ({
      date_from: dateFrom,
      date_to: dateTo,
      rating_bucket: ratingBucket || undefined,
      selection_key: selectionKey || undefined,
      normalized_market: normalizedMarket || undefined,
      evaluation_status: evaluationStatus || undefined,
      country_name: countryName || undefined,
      league_name: leagueName || undefined,
      only_current: true,
      include_diagnostics: true,
    }),
    [
      dateFrom,
      dateTo,
      ratingBucket,
      selectionKey,
      normalizedMarket,
      evaluationStatus,
      countryName,
      leagueName,
    ],
  )

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [summaryRes, activationsRes] = await Promise.all([
        getKpiSignalsSummary(filters),
        getKpiSignalsActivations({ ...filters, limit: 500, offset: 0 }),
      ])
      setSummary(summaryRes)
      setActivations(activationsRes.activations)
    } catch (err) {
      toast.error(formatFetchError(err))
    } finally {
      setLoading(false)
    }
  }, [filters])

  const runSync = useCallback(async () => {
    setActionLoading(true)
    try {
      const res = await backfillKpiSignals({
        date_from: dateFrom,
        date_to: dateTo,
        only_missing: false,
        evaluate_after: true,
      })
      if (res.status === 'partial') {
        toast.warning(
          `Sincronizzazione KPI completata parzialmente: ${res.fixtures} fixture elaborate, ${res.failed} errori.`,
        )
      } else {
        toast.success(`Sincronizzazione KPI completata (${String(res.created ?? 0)} creati)`)
      }
      await loadAll()
    } catch (err) {
      if (err instanceof AdminHttpError && err.body && typeof err.body === 'object') {
        const body = err.body as { message?: string; code?: string }
        if (body.message) {
          toast.error(body.message)
          return
        }
      }
      toast.error(formatFetchError(err))
    } finally {
      setActionLoading(false)
    }
  }, [dateFrom, dateTo, loadAll])

  const runRevaluate = useCallback(async () => {
    setActionLoading(true)
    try {
      await revaluateKpiSignals({ date_from: dateFrom, date_to: dateTo })
      toast.success('Rivalutazione KPI completata')
      await loadAll()
    } catch (err) {
      toast.error(formatFetchError(err))
    } finally {
      setActionLoading(false)
    }
  }, [dateFrom, dateTo, loadAll])

  const exportCsv = useCallback(() => {
    window.open(buildKpiSignalsExportUrl(filters), '_blank', 'noopener,noreferrer')
  }, [filters])

  return {
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    ratingBucket,
    setRatingBucket,
    selectionKey,
    setSelectionKey,
    normalizedMarket,
    setNormalizedMarket,
    evaluationStatus,
    setEvaluationStatus,
    countryName,
    setCountryName,
    leagueName,
    setLeagueName,
    summary,
    activations,
    loading,
    actionLoading,
    loadAll,
    runSync,
    runRevaluate,
    exportCsv,
  }
}
