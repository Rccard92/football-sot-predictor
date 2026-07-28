import type { HistoricalRunModuleCoverage as Cov } from '../../../lib/cecchinoLabApi'

type Props = { coverage: Record<string, Cov> }

const LABELS: Record<string, string> = {
  historical_kpi: 'KPI storico Bet365',
  signals_a_f: 'Segnali A–F',
  balance: 'Balance',
  goal_intensity: 'Intensità Goal',
  purchasability: 'Acquistabilità',
}

export function HistoricalRunModuleCoveragePanel({ coverage }: Props) {
  return (
    <section>
      <h3 className="mb-3 text-lg font-semibold">Copertura moduli</h3>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        {Object.entries(coverage).map(([key, c]) => (
          <div
            key={key}
            className="rounded-xl border p-3"
            style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
          >
            <div className="text-sm font-medium">{LABELS[key] ?? key}</div>
            <div className="mt-1 text-xs text-[var(--lab-muted)]">
              {c.observation_status} · {c.coverage_pct}%
            </div>
            <div className="mt-2 flex gap-2 text-[11px]">
              <span style={{ color: 'var(--lab-ok)' }}>C {c.complete}</span>
              <span style={{ color: 'var(--lab-warn)' }}>P {c.partial}</span>
              <span style={{ color: 'var(--lab-muted)' }}>N/D {c.unavailable}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
