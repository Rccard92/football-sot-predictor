import { useCallback, useEffect, useRef, useState } from 'react'
import {
  PURCHASABILITY_JOB_POLL_MS,
  formatPurchasabilityJobError,
  getActivePurchasabilityStatisticalJob,
  getPurchasabilityStatisticalJob,
  getPurchasabilityStatisticalJobSummary,
  startPurchasabilityStatisticalJob,
  type PurchasabilityResearchJobStatus,
  type PurchasabilityStatFilters,
  type PurchasabilityStatisticalResearchResponse,
} from '../lib/cecchinoPurchasabilityStatisticalApi'

function defaultRange(): { date_from: string; date_to: string } {
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - 90)
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return { date_from: fmt(from), date_to: fmt(to) }
}

export function useCecchinoPurchasabilityStatisticalResearch() {
  const defaults = defaultRange()
  const [dateFrom, setDateFrom] = useState(defaults.date_from)
  const [dateTo, setDateTo] = useState(defaults.date_to)
  const [selection, setSelection] = useState('')
  const [bootstrapIterations, setBootstrapIterations] = useState(200)
  const [loading, setLoading] = useState(false)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<PurchasabilityStatisticalResearchResponse | null>(null)
  const [job, setJob] = useState<PurchasabilityResearchJobStatus | null>(null)
  const busyRef = useRef(false)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const filters = useCallback((): PurchasabilityStatFilters => {
    return {
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      selection: selection || undefined,
      bootstrap_iterations: bootstrapIterations,
      seed: 42,
    }
  }, [dateFrom, dateTo, selection, bootstrapIterations])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current != null) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const loadSummary = useCallback(async (jobId: string) => {
    setLoadingSummary(true)
    try {
      const summary = await getPurchasabilityStatisticalJobSummary(jobId)
      if (!mountedRef.current) return
      setData(summary)
      setError(null)
    } catch (e) {
      if (!mountedRef.current) return
      setError(formatPurchasabilityJobError(e))
    } finally {
      if (mountedRef.current) {
        setLoadingSummary(false)
        setLoading(false)
        busyRef.current = false
      }
    }
  }, [])

  const pollJob = useCallback(
    (jobId: string) => {
      stopPolling()
      const tick = async () => {
        try {
          const st = await getPurchasabilityStatisticalJob(jobId)
          if (!mountedRef.current) return
          setJob(st)
          if (st.status === 'completed') {
            stopPolling()
            await loadSummary(jobId)
            return
          }
          if (st.status === 'failed') {
            stopPolling()
            setLoading(false)
            busyRef.current = false
            setError(
              st.error_message ||
                'Elaborazione fallita sul backend. Avvia nuovamente la ricerca.',
            )
            return
          }
          pollTimerRef.current = setTimeout(() => {
            void tick()
          }, PURCHASABILITY_JOB_POLL_MS)
        } catch (e) {
          if (!mountedRef.current) return
          stopPolling()
          setLoading(false)
          busyRef.current = false
          setError(formatPurchasabilityJobError(e))
        }
      }
      void tick()
    },
    [loadSummary, stopPolling],
  )

  const load = useCallback(async () => {
    if (busyRef.current) return
    busyRef.current = true
    setLoading(true)
    setError(null)
    try {
      const started = await startPurchasabilityStatisticalJob(filters())
      if (!mountedRef.current) return
      setJob({
        job_id: started.job_id,
        status: started.status,
        filters: filters(),
      })
      if (started.status === 'completed') {
        await loadSummary(started.job_id)
        return
      }
      pollJob(started.job_id)
    } catch (e) {
      if (!mountedRef.current) return
      busyRef.current = false
      setLoading(false)
      setError(formatPurchasabilityJobError(e))
    }
  }, [filters, loadSummary, pollJob])

  useEffect(() => {
    mountedRef.current = true
    let cancelled = false
    ;(async () => {
      try {
        const active = await getActivePurchasabilityStatisticalJob()
        if (cancelled || !mountedRef.current) return
        const j = active.job
        if (j && (j.status === 'queued' || j.status === 'running')) {
          setJob(j)
          setLoading(true)
          busyRef.current = true
          pollJob(j.job_id)
        }
      } catch {
        // silent: tab open without active job is fine
      }
    })()
    return () => {
      cancelled = true
      mountedRef.current = false
      stopPolling()
    }
  }, [pollJob, stopPolling])

  const busy =
    loading ||
    loadingSummary ||
    job?.status === 'queued' ||
    job?.status === 'running'

  return {
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    selection,
    setSelection,
    bootstrapIterations,
    setBootstrapIterations,
    loading: busy,
    loadingSummary,
    error,
    data,
    job,
    filters,
    load,
  }
}
