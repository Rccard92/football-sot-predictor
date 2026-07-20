import { useEffect, useId, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  getBalanceEmpiricalAnalysisJob,
  startBalanceEmpiricalAnalysisJob,
  type BalanceEmpiricalAnalysisJobStatus,
} from '../../../lib/cecchinoModuleMonitoringApi'
import { AdminHttpError } from '../../../lib/api'
import { createAuditRequestGuard } from '../auditRequestGuard'
import { MonitoringExportMenu } from '../MonitoringExportMenu'
import { MOTION_FAST } from '../moduleMonitoringUi'
import {
  BOOTSTRAP_ITERATIONS_DEFAULT,
  BOOTSTRAP_OPTIONS,
  DEFAULT_POLL_AFTER_MS,
  JOB_409_ATTACHED_MESSAGE,
  TIMELINE_PHASES,
  abbreviateJobId,
  buildJobJsonFilename,
  clampBootstrapIterations,
  clearJobSession,
  downloadJobResultJson,
  extractResultSummary,
  filtersMatch,
  formatBalanceEmpiricalJobError,
  formatElapsedClock,
  isJobAlreadyRunning409,
  loadJobSession,
  mapJobStatusIt,
  parseActiveJobIdFrom409,
  resolveNumericProgress,
  saveJobSession,
  timelinePhaseStates,
  type BalanceJobFiltersSnapshot,
} from './balanceEmpiricalAnalysisJobHelpers'

type Props = {
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  cohortFilter?: string
  /** Compact mode for Export view */
  compact?: boolean
}

function currentFilters(
  dateFrom: string,
  dateTo: string,
  competitionId: number | null | undefined,
  cohortFilter: string | undefined,
): BalanceJobFiltersSnapshot {
  return {
    dateFrom,
    dateTo,
    competitionId: competitionId ?? null,
    cohortFilter: cohortFilter || 'all',
  }
}

export function BalanceEmpiricalAnalysisJobPanel({
  dateFrom,
  dateTo,
  competitionId = null,
  cohortFilter = 'all',
  compact = false,
}: Props) {
  const titleId = useId()
  const startGuard = useRef(createAuditRequestGuard())
  const pollAbortRef = useRef<AbortController | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const jobIdRef = useRef<string | null>(null)
  const pollMsRef = useRef(DEFAULT_POLL_AFTER_MS)
  const mountedRef = useRef(true)

  const [bootstrap, setBootstrap] = useState(() => {
    const saved = loadJobSession()
    const f = currentFilters(dateFrom, dateTo, competitionId, cohortFilter)
    if (
      saved &&
      filtersMatch(saved.filters, f) &&
      typeof saved.bootstrap_iterations === 'number'
    ) {
      return clampBootstrapIterations(saved.bootstrap_iterations)
    }
    return BOOTSTRAP_ITERATIONS_DEFAULT
  })
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<BalanceEmpiricalAnalysisJobStatus | null>(null)
  const [starting, setStarting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [elapsedLocal, setElapsedLocal] = useState<number | null>(null)

  const filters = currentFilters(dateFrom, dateTo, competitionId, cohortFilter)
  const status = typeof job?.status === 'string' ? job.status : null
  const busy =
    starting || status === 'queued' || status === 'running' || startGuard.current.isInFlight()

  function stopPolling() {
    if (pollTimerRef.current != null) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
    try {
      pollAbortRef.current?.abort()
    } catch {
      /* ignore */
    }
    pollAbortRef.current = null
  }

  function persistJob(id: string, pollMs?: number) {
    saveJobSession({
      job_id: id,
      filters,
      timestamp: new Date().toISOString(),
      poll_after_ms: pollMs ?? pollMsRef.current,
      bootstrap_iterations: bootstrap,
    })
  }

  async function pollOnce(id: string): Promise<BalanceEmpiricalAnalysisJobStatus | null> {
    const ac = new AbortController()
    pollAbortRef.current = ac
    try {
      const payload = await getBalanceEmpiricalAnalysisJob(id, { signal: ac.signal })
      if (!mountedRef.current || jobIdRef.current !== id) return null
      setJob(payload)
      setErrorMsg(null)
      if (typeof payload.elapsed_seconds === 'number') {
        setElapsedLocal(payload.elapsed_seconds)
      }
      const st = String(payload.status || '')
      if (st === 'completed' || st === 'failed') {
        stopPolling()
        return payload
      }
      const delay =
        typeof payload.poll_after_ms === 'number' && payload.poll_after_ms > 0
          ? payload.poll_after_ms
          : pollMsRef.current
      pollTimerRef.current = setTimeout(() => {
        void pollOnce(id)
      }, delay)
      return payload
    } catch (err) {
      if (!mountedRef.current || jobIdRef.current !== id) return null
      if (err instanceof DOMException && err.name === 'AbortError') return null
      if (err instanceof AdminHttpError && err.status === 404) {
        stopPolling()
        clearJobSession()
        setJobId(null)
        jobIdRef.current = null
        setJob(null)
        setErrorMsg(formatBalanceEmpiricalJobError(err))
        return null
      }
      setErrorMsg(formatBalanceEmpiricalJobError(err))
      // rete/errore transient: ritenta
      pollTimerRef.current = setTimeout(() => {
        void pollOnce(id)
      }, pollMsRef.current)
      return null
    }
  }

  function attachJob(id: string, pollMs?: number) {
    stopPolling()
    jobIdRef.current = id
    setJobId(id)
    if (pollMs != null && pollMs > 0) pollMsRef.current = pollMs
    persistJob(id, pollMsRef.current)
    void pollOnce(id)
  }

  // Restore session + cleanup — no auto-start (solo ripresa polling se job già noto)
  useEffect(() => {
    mountedRef.current = true
    const guard = startGuard.current
    let cancelled = false
    const saved = loadJobSession()
    if (saved && filtersMatch(saved.filters, filters)) {
      if (typeof saved.poll_after_ms === 'number') {
        pollMsRef.current = saved.poll_after_ms
      }
      // Defer: evita setState sincrono nell'effect (react-hooks/set-state-in-effect)
      queueMicrotask(() => {
        if (!cancelled) attachJob(saved.job_id, saved.poll_after_ms)
      })
    } else if (saved && !filtersMatch(saved.filters, filters)) {
      clearJobSession()
    }
    return () => {
      cancelled = true
      mountedRef.current = false
      stopPolling()
      guard.abort()
    }
    // Solo al mount / cambio filtri strutturali
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restore once per filter set
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  // Elapsed locale mentre running (da started_at o elapsed_seconds backend)
  useEffect(() => {
    if (status !== 'queued' && status !== 'running') return
    const t0 = Date.now()
    const base =
      typeof job?.elapsed_seconds === 'number' && Number.isFinite(job.elapsed_seconds)
        ? job.elapsed_seconds
        : 0
    const iv = setInterval(() => {
      setElapsedLocal(base + (Date.now() - t0) / 1000)
    }, 1000)
    return () => clearInterval(iv)
  }, [status, job?.elapsed_seconds, jobId])

  async function handleStart() {
    const flight = startGuard.current.begin()
    if (!flight) return
    setStarting(true)
    setErrorMsg(null)
    try {
      const body = {
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId ?? null,
        source_cohort: cohortFilter || 'all',
        bootstrap_iterations: clampBootstrapIterations(bootstrap),
      }
      const res = await startBalanceEmpiricalAnalysisJob(body, {
        signal: flight.signal,
      })
      if (!startGuard.current.isCurrent(flight.requestId)) return
      const pollMs =
        typeof res.poll_after_ms === 'number' && res.poll_after_ms > 0
          ? res.poll_after_ms
          : DEFAULT_POLL_AFTER_MS
      toast.success('Analisi statistica avviata')
      attachJob(res.job_id, pollMs)
    } catch (err) {
      if (!startGuard.current.isCurrent(flight.requestId)) return
      if (err instanceof AdminHttpError && isJobAlreadyRunning409(err.status, err.body)) {
        const active = parseActiveJobIdFrom409(err.body)
        if (active) {
          toast.message(JOB_409_ATTACHED_MESSAGE)
          attachJob(active, DEFAULT_POLL_AFTER_MS)
          return
        }
      }
      const msg = formatBalanceEmpiricalJobError(err)
      setErrorMsg(msg)
      toast.error(msg)
    } finally {
      startGuard.current.end(flight.requestId)
      setStarting(false)
    }
  }

  function handleDownloadJson() {
    if (!job) return
    const name = buildJobJsonFilename(jobId || 'unknown', dateFrom, dateTo)
    downloadJobResultJson(job, name)
    toast.success('Download JSON avviato')
  }

  const phases = timelinePhaseStates(status)
  const numericProgress = resolveNumericProgress(job as Record<string, unknown> | null)
  const summary = status === 'completed' ? extractResultSummary(job as Record<string, unknown>) : null
  const versions = {
    analysis: dashStr(job?.analysis_version),
    policy: dashStr(job?.policy_version),
    dataset: dashStr(job?.dataset_version),
  }

  if (compact) {
    return (
      <div className="rounded-2xl border border-violet-100 bg-gradient-to-r from-violet-50/60 to-indigo-50/40 p-3 shadow-sm">
        <p className="text-sm font-semibold text-slate-900">Ultimo job statistico</p>
        {jobId ? (
          <dl className="mt-2 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">
            <div>
              <dt className="inline text-slate-500">ID · </dt>
              <dd className="inline font-mono">{abbreviateJobId(jobId)}</dd>
            </div>
            <div>
              <dt className="inline text-slate-500">Stato · </dt>
              <dd className="inline" aria-live="polite">
                {mapJobStatusIt(status)}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="inline text-slate-500">Periodo · </dt>
              <dd className="inline">
                {dateFrom} → {dateTo}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="mt-1 text-xs text-slate-500">
            Nessun job in sessione. Avvia l’analisi dalla vista Overview.
          </p>
        )}
      </div>
    )
  }

  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={MOTION_FAST}
      aria-labelledby={titleId}
      className="rounded-2xl border border-violet-100 bg-gradient-to-br from-violet-50/90 via-white to-indigo-50/60 p-4 shadow-sm"
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 id={titleId} className="text-base font-semibold text-slate-900">
            Analisi statistica completa
          </h3>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Esegue bootstrap, calibrazione, test statistici e analisi di stabilità dei quattro
            pilastri sul campione selezionato.
          </p>
        </div>
      </div>

      <div
        className="mt-3 rounded-xl border border-indigo-100 bg-indigo-50/70 px-3 py-2 text-sm text-indigo-950"
        role="note"
      >
        Il job non modifica formule, soglie, classi o Segnali.
      </div>

      <dl className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2 lg:grid-cols-3">
        <MetaItem label="Periodo" value={`${dateFrom} → ${dateTo}`} />
        <MetaItem label="Coorte" value={cohortFilter || 'all'} />
        <MetaItem
          label="Competizione"
          value={competitionId != null ? String(competitionId) : 'Tutte'}
        />
        <MetaItem label="Iterazioni bootstrap" value={String(bootstrap)} />
        <MetaItem label="Dataset version" value={versions.dataset} />
        <MetaItem label="Analysis version" value={versions.analysis} />
        <MetaItem label="Policy version" value={versions.policy} />
      </dl>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="flex min-w-[220px] flex-col gap-1 text-sm text-slate-700">
          <span className="font-medium">Bootstrap</span>
          <select
            value={bootstrap}
            disabled={busy}
            onChange={(e) => setBootstrap(clampBootstrapIterations(Number(e.target.value)))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-600 disabled:opacity-60"
          >
            {BOOTSTRAP_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
                {'recommended' in o && o.recommended ? ' (Consigliato)' : ''}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          disabled={busy}
          aria-busy={starting || undefined}
          aria-label={starting ? 'Avvio analisi in corso' : 'Avvia analisi completa'}
          onClick={() => void handleStart()}
          className="inline-flex items-center justify-center rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {starting ? 'Avvio…' : 'Avvia analisi completa'}
        </button>
      </div>

      <div className="mt-2 text-xs text-slate-500" aria-live="polite">
        Stato:{' '}
        <span className="font-medium text-slate-800">{mapJobStatusIt(status)}</span>
        {jobId ? (
          <>
            {' '}
            · Job <span className="font-mono">{abbreviateJobId(jobId)}</span>
          </>
        ) : null}
        {status === 'queued' || status === 'running' ? (
          <>
            {' '}
            · Tempo {formatElapsedClock(elapsedLocal)}
            {job?.progress_message ? ` · ${String(job.progress_message)}` : null}
            {numericProgress != null ? ` · ${numericProgress}%` : null}
          </>
        ) : null}
      </div>

      <AnimatePresence>
        {(status === 'queued' || status === 'running') && (
          <motion.ol
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4 space-y-2 overflow-hidden"
            aria-label="Fasi analisi"
          >
            {TIMELINE_PHASES.map((label, i) => {
              const st = phases[i]
              return (
                <li
                  key={label}
                  className="flex items-center gap-2 text-sm text-slate-700"
                >
                  <PhaseDot state={st} />
                  <span>
                    {label}
                    {st === 'active' || st === 'indeterminate' ? (
                      <span className="sr-only"> in corso</span>
                    ) : null}
                    {st === 'done' ? <span className="sr-only"> completata</span> : null}
                  </span>
                  {(st === 'active' || st === 'indeterminate') && (
                    <span
                      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-violet-300 border-t-violet-700"
                      aria-hidden
                    />
                  )}
                </li>
              )
            })}
          </motion.ol>
        )}
      </AnimatePresence>

      {errorMsg ? (
        <p
          role="alert"
          className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900"
        >
          {errorMsg}
        </p>
      ) : null}

      {status === 'failed' && job?.error_message ? (
        <p role="alert" className="mt-3 text-sm text-rose-800">
          {String(job.error_message)}
        </p>
      ) : null}

      {status === 'completed' && summary ? (
        <div className="mt-4 space-y-3">
          <h4 className="text-sm font-semibold text-slate-900">Risultato</h4>
          <dl className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
            <MetaItem label="Job ID" value={summary.jobIdShort} />
            <MetaItem label="Avvio" value={summary.startedAt} />
            <MetaItem label="Completamento" value={summary.completedAt} />
            <MetaItem label="Durata" value={summary.duration} />
            <MetaItem label="Righe analizzate" value={summary.rowsAnalyzed} />
            <MetaItem label="Bootstrap" value={summary.bootstrapIterations} />
            <MetaItem label="Bootstrap richiesto" value={summary.bootstrapRequested} />
            <MetaItem label="Bootstrap effettivo" value={summary.bootstrapEffective} />
            <MetaItem label="Evidence scope" value={summary.evidenceScope} />
            <MetaItem label="Status F36" value={summary.statusF36} />
            <MetaItem label="Status Dominanza" value={summary.statusDominance} />
            <MetaItem label="Status Credibilità X" value={summary.statusCredibilityX} />
            <MetaItem label="Status Gap" value={summary.statusGap} />
            <MetaItem label="Warning count" value={summary.warningCount} />
          </dl>

          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <button
              type="button"
              onClick={handleDownloadJson}
              className="inline-flex items-center justify-center rounded-xl border border-violet-200 bg-white px-4 py-2.5 text-sm font-semibold text-violet-900 shadow-sm hover:bg-violet-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-600"
            >
              Scarica risultato statistico JSON
            </button>
            <div className="inline-flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-600">
                Scarica pacchetto Balance v8
              </span>
              <MonitoringExportMenu
                moduleKey="balance-v5"
                dateFrom={dateFrom}
                dateTo={dateTo}
                competitionId={competitionId}
                sourceCohort={cohortFilter}
              />
            </div>
          </div>
          <p className="text-xs text-slate-500">
            Il JSON contiene il risultato del job. Lo ZIP contiene dataset, analisi, policy, health
            ed export scientifici completi.
          </p>
        </div>
      ) : null}
    </motion.section>
  )
}

function dashStr(v: unknown): string {
  if (v == null || v === '') return '—'
  return String(v)
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-white/70 px-2.5 py-1.5">
      <dt className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-0.5 break-all text-slate-800">{value}</dd>
    </div>
  )
}

function PhaseDot({
  state,
}: {
  state: 'pending' | 'active' | 'done' | 'indeterminate'
}) {
  const cls =
    state === 'done'
      ? 'bg-violet-600'
      : state === 'active' || state === 'indeterminate'
        ? 'bg-indigo-500 ring-2 ring-indigo-200'
        : 'bg-slate-300'
  return (
    <span
      className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${cls}`}
      aria-hidden
    />
  )
}
