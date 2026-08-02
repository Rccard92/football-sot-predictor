import { Link } from 'react-router-dom'
import {
  historicalScanStatusLabel,
  type HistoricalKpiSignalsSummary,
} from '../../../lib/cecchinoLabApi'
import { scopeLabel } from './historicalKpiUtils'

type Props = {
  run: HistoricalKpiSignalsSummary['run']
}

export function HistoricalKpiSignalsHeader({ run }: Props) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <Link
          to={`/cecchino-lab/historical-scans/${run.run_id}`}
          className="text-xs text-[var(--lab-cyan)] underline-offset-2 hover:underline"
        >
          ← Hub run #{run.run_id}
        </Link>
        <h1
          className="mt-2 text-2xl font-semibold tracking-tight"
          style={{ fontFamily: 'IBM Plex Sans, sans-serif' }}
        >
          Analisi KPI storico
        </h1>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--lab-muted)]">
          <span className="lab-badge-muted rounded px-2 py-0.5">
            Run #{run.run_id}
          </span>
          <span className="rounded px-2 py-0.5" style={{ background: 'var(--lab-surface-2)' }}>
            {run.season_label}
          </span>
          <span className="lab-badge-muted rounded px-2 py-0.5">
            {historicalScanStatusLabel(run.status)}
          </span>
          <span className="rounded px-2 py-0.5" style={{ background: 'var(--lab-surface-2)' }}>
            {scopeLabel(run.scope, run.is_partial_run)}
          </span>
          <span className="rounded px-2 py-0.5 lab-quote-real">
            Sorgente storica Bet365
          </span>
          <span className="rounded px-2 py-0.5" style={{ background: 'var(--lab-surface-2)' }}>
            Nessuna API esterna
          </span>
        </div>
        <p className="mt-2 max-w-2xl text-sm text-[var(--lab-muted)]">
          Prestazioni osservate sui segnali KPI del panel v2, filtrate per fascia rating e mercato.
          Dati congelati a fine run storico.
        </p>
      </div>
    </header>
  )
}
