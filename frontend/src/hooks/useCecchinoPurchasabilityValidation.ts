import { useCallback, useEffect, useRef, useState } from 'react'
import {
  PURCHASABILITY_VALIDATION_POLL_MS,
  formatValidationJobError,
  getPurchasabilityValidationHealth,
  getPurchasabilityValidationJob,
  getPurchasabilityValidationJobResult,
  getPurchasabilityValidationReadiness,
  getPurchasabilityValidationSummary,
  startPurchasabilityValidationJob,
  type PurchasabilityValidationFilters,
  type PurchasabilityValidationHealth,
  type PurchasabilityValidationJobStatus,
  type PurchasabilityValidationReadiness,
  type PurchasabilityValidationSummary,
} from '../lib/cecchinoPurchasabilityValidationApi'

function defaultRange(): { date_from: string; date_to: string } {
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - 90)
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return { date_from: fmt(from), date_to: fmt(to) }
}

export function useCecchinoPurchasabilityValidation() {
  const defaults = defaultRange()
  const [dateFrom, setDateFrom] = useState(defaults.date_from)
  const [dateTo, setDateTo] = useState(defaults.date_to)
  const [marketKey, setMarketKey] = useState('')
  const [bootstrapIterations, setBootstrapIterations] = useState(200)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<PurchasabilityValidationHealth | null>(null)
  const [summary, setSummary] = useState<PurchasabilityValidationSummary | null>(null)
  const [readiness, setReadiness] = useState<PurchasabilityValidationReadiness | null>(null)
  const [job, setJob] = useState<PurchasabilityValidationJobStatus | null>(null)
  const busyRef = useRef(false)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const filters = useCallback((): PurchasabilityValidationFilters => {
    return {
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      market_key: marketKey || undefined,
      bootstrap_iterations: bootstrapIterations,
      promotion_eligible_only: true,
    }
  }, [dateFrom, dateTo, marketKey, bootstrapIterations])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current != null) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const loadSync = useCallback(async () => {
    if (busyRef.current) return
    busyRef.current = true
    setLoading(true)
    setError(null)
    try {
      const f = filters()
      const [h, s, r] = await Promise.all([
        getPurchasabilityValidationHealth(f),
        getPurchasabilityValidationSummary(f),
        getPurchasabilityValidationReadiness(f),
      ])
      if (!mountedRef.current) return
      setHealth(h)
      setSummary(s)
      setReadiness(r)
    } catch (err) {
      if (!mountedRef.current) return
      setError(formatValidationJobError(err))
    } finally {
      busyRef.current = false
      if (mountedRef.current) setLoading(false)
    }
  }, [filters])

  const pollJob = useCallback(
    (jobId: string) => {
      stopPolling()
      const tick = async () => {
        try {
          const st = await getPurchasabilityValidationJob(jobId)
          if (!mountedRef.current) return
          setJob(st)
          if (st.status === 'completed') {
            const result = await getPurchasabilityValidationJobResult(jobId)
            if (!mountedRef.current) return
            if (result.summary) setSummary(result.summary)
            if (result.readiness) setReadiness(result.readiness)
            setLoading(false)
            return
          }
          if (st.status === 'failed') {
            setError(st.error_message || st.error_code || 'job_failed')
            setLoading(false)
            return
          }
          pollTimerRef.current = setTimeout(
            () => void tick(),
            st.poll_after_ms || PURCHASABILITY_VALIDATION_POLL_MS,
          )
        } catch (err) {
          if (!mountedRef.current) return
          setError(formatValidationJobError(err))
          setLoading(false)
        }
      }
      void tick()
    },
    [stopPolling],
  )

  const startJob = useCallback(async () => {
    stopPolling()
    setLoading(true)
    setError(null)
    try {
      const started = await startPurchasabilityValidationJob(filters())
      setJob({
        job_id: started.job_id,
        status: started.status,
        poll_after_ms: started.poll_after_ms,
      })
      pollJob(started.job_id)
    } catch (err) {
      setError(formatValidationJobError(err))
      setLoading(false)
    }
  }, [filters, pollJob, stopPolling])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      stopPolling()
    }
  }, [stopPolling])

  return {
    dateFrom,
    dateTo,
    marketKey,
    bootstrapIterations,
    setDateFrom,
    setDateTo,
    setMarketKey,
    setBootstrapIterations,
    loading,
    error,
    health,
    summary,
    readiness,
    job,
    filters,
    loadSync,
    startJob,
  }
}
