import type { CecchinoTodayScanJob } from '../../lib/cecchinoTodayApi'
import { SCAN_STEP_LABELS } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding } from './cecchinoTodayStyles'

type Props = {
  job: CecchinoTodayScanJob
}

function stepLabel(step: string | null): string {
  if (!step) return 'In attesa…'
  return SCAN_STEP_LABELS[step] ?? step
}

export function CecchinoTodayScanProgressCard({ job }: Props) {
  const pct = job.progress_pct ?? 0
  const isRunning = job.status === 'queued' || job.status === 'running'
  const isFailed = job.status === 'failed'
  const isCompleted = job.status === 'completed'

  return (
    <section
      className={`${todayCard} ${todayCardPadding} ${
        isFailed ? 'border-red-200 bg-red-50/40' : isCompleted ? 'border-emerald-200 bg-emerald-50/40' : 'border-blue-200 bg-blue-50/40'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">
            {isRunning
              ? 'Scansione giornata in corso'
              : isCompleted
                ? 'Scansione completata'
                : isFailed
                  ? 'Scansione non riuscita'
                  : 'Scansione giornata'}
          </h3>
          <p className="mt-1 text-xs text-slate-600">
            {job.scan_date} — {stepLabel(job.current_step)}
          </p>
        </div>
        {isRunning ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-600 px-2.5 py-1 text-xs font-semibold text-white">
            <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
            Scanning
          </span>
        ) : null}
      </div>

      {isRunning ? (
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs text-slate-600">
            <span>
              Fixture {job.fixtures_checked}
              {job.progress_total != null ? ` / ${job.progress_total}` : ''}
            </span>
            <span>{pct.toFixed(1)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-blue-600 transition-all duration-300"
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
        {job.started_at ? (
          <span className="rounded bg-white/80 px-2 py-1 text-slate-500">
            Avvio: {new Date(job.started_at).toLocaleTimeString('it-IT')}
          </span>
        ) : null}
      </div>

      {(job.warnings?.length ?? 0) > 0 && isRunning ? (
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
