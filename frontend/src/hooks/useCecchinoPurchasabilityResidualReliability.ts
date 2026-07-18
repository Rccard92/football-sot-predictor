import { useCallback, useEffect, useRef, useState } from 'react'
import {
  PURCHASABILITY_JOB_POLL_MS,
  formatResidualJobError,
  getActivePurchasabilityResidualJob,
  getPurchasabilityResidualJob,
  getPurchasabilityResidualJobResult,
  getPurchasabilityResidualJobSummary,
  startPurchasabilityResidualJob,
  type PurchasabilityResearchJobStatus,
  type PurchasabilityResidualFilters,
  type PurchasabilityResidualReliabilityResponse,
} from '../lib/cecchinoPurchasabilityResidualApi'

function defaultRange(): { date_from: string; date_to: string } {
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - 90)
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return { date_from: fmt(from), date_to: fmt(to) }
}

function isResidualJob(job: PurchasabilityResearchJobStatus | null | undefined): boolean {
  if (!job) return false
  const mode =
    (job as { research_mode?: string }).research_mode ||
    (job.filters as { research_mode?: string } | undefined)?.research_mode
  return mode === 'phase2a_residual_reliability'
}

export function useCecchinoPurchasabilityResidualReliability() {
  const defaults = defaultRange()
  const [dateFrom, setDateFrom] = useState(defaults.date_from)
  const [dateTo, setDateTo] = useState(defaults.date_to)
  const [selection, setSelection] = useState('')
  const [bootstrapIterations, setBootstrapIterations] = useState(200)
  const [loading, setLoading] = useState(false)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [loadingResult, setLoadingResult] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailWarning, setDetailWarning] = useState<string | null>(null)
  const [data, setData] = useState<PurchasabilityResidualReliabilityResponse | null>(null)
  const [job, setJob] = useState<PurchasabilityResearchJobStatus | null>(null)
  const busyRef = useRef(false)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const filters = useCallback((): PurchasabilityResidualFilters => {
    return {
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      selection: selection || undefined,
      bootstrap_iterations: bootstrapIterations,
      seed: 42,
      research_mode: 'phase2a_residual_reliability',
    }
  }, [dateFrom, dateTo, selection, bootstrapIterations])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current != null) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const loadCompletedPayload = useCallback(async (jobId: string) => {
    setLoadingSummary(true)
    setDetailWarning(null)
    try {
      const summary = await getPurchasabilityResidualJobSummary(jobId)
      if (!mountedRef.current) return
      setData(summary)
      setError(null)
      setLoadingSummary(false)
      setLoadingResult(true)
      try {
        const full = await getPurchasabilityResidualJobResult(jobId)
        if (!mountedRef.current) return
        setData(full)
        setDetailWarning(null)
      } catch {
        if (!mountedRef.current) return
        setDetailWarning(
          'Risultato sintetico disponibile, dettaglio completo non caricato.',
        )
      } finally {
        if (mountedRef.current) setLoadingResult(false)
      }
    } catch (e) {
      if (!mountedRef.current) return
      setError(formatResidualJobError(e))
      setLoadingSummary(false)
    } finally {
      if (mountedRef.current) {
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
          const st = await getPurchasabilityResidualJob(jobId)
          if (!mountedRef.current) return
          setJob(st)
          if (st.status === 'completed') {
            stopPolling()
            await loadCompletedPayload(jobId)
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
          setError(formatResidualJobError(e))
        }
      }
      void tick()
    },
    [loadCompletedPayload, stopPolling],
  )

  const load = useCallback(async () => {
    if (busyRef.current) return
    busyRef.current = true
    setLoading(true)
    setError(null)
    setDetailWarning(null)
    try {
      const started = await startPurchasabilityResidualJob(filters())
      if (!mountedRef.current) return
      setJob({
        job_id: started.job_id,
        status: started.status,
        filters: filters(),
        research_mode: 'phase2a_residual_reliability',
      } as PurchasabilityResearchJobStatus)
      if (started.status === 'completed') {
        await loadCompletedPayload(started.job_id)
        return
      }
      pollJob(started.job_id)
    } catch (e) {
      if (!mountedRef.current) return
      busyRef.current = false
      setLoading(false)
      setError(formatResidualJobError(e))
    }
  }, [filters, loadCompletedPayload, pollJob])

  useEffect(() => {
    mountedRef.current = true
    let cancelled = false
    ;(async () => {
      try {
        const active = await getActivePurchasabilityResidualJob()
        if (cancelled || !mountedRef.current) return
        const j = active.job
        if (j && isResidualJob(j) && (j.status === 'queued' || j.status === 'running')) {
          setJob(j)
          setLoading(true)
          busyRef.current = true
          pollJob(j.job_id)
        }
      } catch {
        // silent
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
    loadingResult ||
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
    loadingResult,
    error,
    detailWarning,
    data,
    job,
    filters,
    load,
  }
}
