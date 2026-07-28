import { Link } from 'react-router-dom'
import {
  historicalScanStatusLabel,
  type HistoricalRunDashboardOverview,
} from '../../../lib/cecchinoLabApi'
import { HistoricalRunReportMenu } from './HistoricalRunReportMenu'

type Props = {
  overview: HistoricalRunDashboardOverview
  competitions?: string[]
}

function scopeLabel(run: HistoricalRunDashboardOverview['run']): string {
  if (run.run_scope === 'balanced_pilot' || run.scope === 'balanced_pilot') {
    return 'Pilota bilanciato'
  }
  if (run.is_partial_run || run.run_scope === 'pilot' || run.scope === 'pilot') {
    return 'Test tecnico / pilota'
  }
  return 'Completa'
}

export function HistoricalRunHeader({ overview, competitions }: Props) {
  const run = overview.run
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <Link
          to="/cecchino-lab"
          className="text-xs text-[var(--lab-cyan)] underline-offset-2 hover:underline"
        >
          ← Cecchino Lab
        </Link>
        <h1
          className="mt-2 text-2xl font-semibold tracking-tight"
          style={{ fontFamily: 'IBM Plex Sans, sans-serif' }}
        >
          Analisi run #{run.run_id} · {run.season_label}
        </h1>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--lab-muted)]">
          <span className="lab-badge-muted rounded px-2 py-0.5">
            {historicalScanStatusLabel(run.status)}
          </span>
          <span className="rounded px-2 py-0.5" style={{ background: 'var(--lab-surface-2)' }}>
            {scopeLabel(run)}
          </span>
          <span>scan {run.scan_version}</span>
          {run.source_git_commit ? (
            <span>commit {run.source_git_commit.slice(0, 10)}</span>
          ) : null}
          <span>Bet365 storico · Betfair Today invariato</span>
        </div>
        <p className="mt-2 max-w-2xl text-sm text-[var(--lab-muted)]">
          Prestazioni osservate su mercati indipendenti. Nessun profitto complessivo aggregato.
          Dati congelati a fine run.
        </p>
      </div>
      <HistoricalRunReportMenu runId={run.run_id} competitions={competitions} />
    </header>
  )
}
