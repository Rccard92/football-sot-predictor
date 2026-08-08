import { useEffect, useMemo, useState } from 'react'
import type { CecchinoTodayScanJob } from '../../lib/cecchinoTodayApi'
import {
  SCAN_STEP_LABELS,
  computeScanJobProgressPct,
  getScanJobApiMetrics,
} from '../../lib/cecchinoTodayApi'
import { CecchinoTodayBookCoveragePanel } from './CecchinoTodayBookCoveragePanel'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  job: CecchinoTodayScanJob
}

function stepLabel(step: string | null): string {
  if (!step) return 'In attesa…'
  return SCAN_STEP_LABELS[step] ?? step
}

function formatElapsed(startedAt: string | null, nowMs: number): string | null {
  if (!startedAt) return null
  const startMs = new Date(startedAt).getTime()
  if (Number.isNaN(startMs)) return null
  const seconds = Math.max(0, Math.floor((nowMs - startMs) / 1000))
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export function isHistoricalBudgetStop(status: string): boolean {
  return status === 'partial_stopped_budget' || status === 'failed_budget_guard'
}

export function isProviderQuotaExhausted(status: string): boolean {
  return status === 'provider_quota_exhausted'
}

export function scanJobTitle(job: CecchinoTodayScanJob): string {
  const { status } = job
  if (status === 'queued' || status === 'running') return 'Scansione in corso'
  if (status === 'skipped_concurrent_scan') return 'Scansione saltata (concorrenza)'
  if (status === 'completed') return 'Scansione completata'
  if (isProviderQuotaExhausted(status)) return 'Scansione interrotta: richieste API esaurite'
  if (isHistoricalBudgetStop(status)) return 'Vecchio arresto preventivo per budget locale'
  if (status === 'failed_timeout') return 'Scansione interrotta per timeout'
  if (status === 'interrupted') return 'Scansione interrotta dal processo'
  if (status === 'failed' || status === 'cancelled') return 'Scansione interrotta'
  return 'Scansione giornata'
}

export function CecchinoTodayScanProgressCard({ job }: Props) {
  const [nowMs, setNowMs] = useState(() => Date.now())
  const pct = computeScanJobProgressPct(job)
  const apiMetrics = getScanJobApiMetrics(job)
  const isRunning = job.status === 'queued' || job.status === 'running'
  const isQuotaStop = isProviderQuotaExhausted(job.status)
  const isHistoricalBudget = isHistoricalBudgetStop(job.status)
  const isSkippedConcurrent = job.status === 'skipped_concurrent_scan'
  const isTimeout = job.status === 'failed_timeout'
  const isInterrupted = job.status === 'interrupted'
  const isFailed =
    job.status === 'failed' ||
    job.status === 'cancelled' ||
    isQuotaStop ||
    isHistoricalBudget ||
    isTimeout ||
    isInterrupted
  const isCompleted = job.status === 'completed' || isSkippedConcurrent
  const autoScan = job.result_summary?.auto_scan
  const executionDate =
    job.result_summary?.execution_date ||
    autoScan?.local_execution_date ||
    null
  const showBar = isRunning || isCompleted || (isFailed && pct > 0)
  const elapsed = useMemo(() => formatElapsed(job.started_at, nowMs), [job.started_at, nowMs])
  const remaining =
    job.result_summary?.fixtures_remaining ??
    job.result_summary?.unprocessed_count ??
    null

  useEffect(() => {
    if (!isRunning || !job.started_at) return
    const id = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [isRunning, job.started_at])

  return (
    <section
      className={`${todayCard} ${todayCardPadding} ${
        isFailed
          ? 'border-red-200 bg-red-50/40'
          : isCompleted
            ? 'border-emerald-200 bg-emerald-50/40'
            : 'border-blue-200 bg-blue-50/40'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{scanJobTitle(job)}</h3>
          <p className="mt-1 text-xs text-slate-600">
            Partite: {job.scan_date} — {stepLabel(job.current_step)}
          </p>
          {executionDate && executionDate !== job.scan_date ? (
            <p className="mt-1 text-xs text-slate-500">Esecuzione API: {executionDate}</p>
          ) : executionDate ? (
            <p className="mt-1 text-xs text-slate-500">Esecuzione: {executionDate}</p>
          ) : null}
          {isQuotaStop ? (
            <p className="mt-1 text-xs text-slate-600">
              API-Football ha confermato che non sono disponibili altre richieste. I risultati già
              elaborati sono stati conservati.
            </p>
          ) : null}
          {isHistoricalBudget ? (
            <p className="mt-1 text-xs text-slate-600">
              Stato storico: arresto locale preventivo (non più usato dalle nuove scansioni).
            </p>
          ) : null}
          {autoScan?.execution_source === 'auto_scan' ? (
            <p className="mt-1 flex flex-wrap gap-1.5 text-[11px] text-slate-500">
              <span>Origine: Automatica</span>
              {autoScan.execution_mode === 'synchronous' ? <span>· Modalità: Sincrona</span> : null}
              {autoScan.execution_slot === 'recovery' ? (
                <span>· Slot: Recupero</span>
              ) : autoScan.execution_slot === 'primary' ? (
                <span>· Slot: Principale</span>
              ) : null}
            </p>
          ) : null}
        </div>
        {isRunning ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-600 px-2.5 py-1 text-xs font-semibold text-white">
            <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
            Scanning
          </span>
        ) : isCompleted ? (
          <span className="inline-flex rounded-full bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white">
            Completata
          </span>
        ) : null}
      </div>

      {showBar ? (
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs text-slate-600">
            <span>
              Fixture {job.progress_current || job.fixtures_checked}
              {job.progress_total != null ? ` / ${job.progress_total}` : ''}
            </span>
            <span>{pct.toFixed(1)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                isFailed ? 'bg-red-500' : isCompleted ? 'bg-emerald-600' : 'bg-blue-600'
              }`}
              style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
            />
          </div>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span className="rounded bg-white/80 px-2 py-1 text-slate-700">
          Eleggibili: {job.eligible_count}
        </span>
        <span className="rounded bg-white/80 px-2 py-1 text-slate-700">
          Escluse: {job.excluded_count}
        </span>
        <span className="rounded bg-white/80 px-2 py-1 text-slate-700">
          Quote controllate: {job.odds_checked}
        </span>
        {remaining != null && remaining > 0 ? (
          <span className="rounded bg-white/80 px-2 py-1 text-slate-700">
            Residue: {remaining}
          </span>
        ) : null}
        {elapsed ? (
          <span className="rounded bg-white/80 px-2 py-1 text-slate-500">Trascorso: {elapsed}</span>
        ) : null}
      </div>

      <div
        className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2"
        data-testid="cecchino-scan-metrics-grid"
      >
        <div
          className="grid gap-1 rounded-lg border border-white/60 bg-white/50 p-3 text-xs text-slate-700"
          data-testid="cecchino-api-consumption-card"
        >
          <p className="font-medium text-slate-800">Consumo API (job)</p>
          <p>API usate: {apiMetrics.apiCallsTotal}</p>
          <p>Odds API: {apiMetrics.oddsApi}</p>
          <p>Odds cache: {apiMetrics.oddsCache}</p>
          <p>Negative cache: {apiMetrics.negativeCache}</p>
          <p>Teams: {apiMetrics.teams}</p>
          <p>Fixtures: {apiMetrics.fixtures}</p>
          {apiMetrics.budgetRemaining != null ? (
            <p>
              Residuo teorico piano (informativo):{' '}
              {apiMetrics.budgetRemaining.toLocaleString('it-IT')}
            </p>
          ) : null}
        </div>

        <CecchinoTodayBookCoveragePanel
          summary={job.result_summary}
          className="!mt-0"
        />
      </div>

      {(job.warnings?.length ?? 0) > 0 && (isRunning || isCompleted || isQuotaStop) ? (
        <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-amber-800">
          {job.warnings.slice(0, 3).map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}

      {(job.errors?.length ?? 0) > 0 && isFailed ? (
        <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-red-800">
          {job.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
