import type { HistoricalKpiSignalsOverall } from '../../../lib/cecchinoLabApi'
import {
  formatOdds,
  formatProfit,
  formatRoi,
  formatWinRate,
  roiColorClass,
} from './historicalKpiUtils'

type Props = {
  title?: string
  metrics: HistoricalKpiSignalsOverall | null
  testId?: string
}

const METRIC_ROWS: Array<{
  key: keyof HistoricalKpiSignalsOverall
  label: string
  format: (v: number | null | undefined) => string
  colorize?: boolean
}> = [
  { key: 'signals_count', label: 'Segnali KPI', format: (v) => String(v ?? '—') },
  { key: 'evaluated_count', label: 'Valutati', format: (v) => String(v ?? '—') },
  { key: 'wins', label: 'Vinti', format: (v) => String(v ?? '—') },
  { key: 'losses', label: 'Persi', format: (v) => String(v ?? '—') },
  { key: 'win_rate_pct', label: 'Win rate', format: formatWinRate },
  { key: 'average_odds_played', label: 'Quota media giocata', format: formatOdds },
  { key: 'average_odds_won', label: 'Quota media presa/vinta', format: formatOdds },
  { key: 'average_odds_void', label: 'Quota void', format: formatOdds },
  { key: 'profit_units', label: 'Profitto unità', format: formatProfit, colorize: true },
  { key: 'roi_pct', label: 'ROI', format: formatRoi, colorize: true },
]

function RibbonBlock({ title, metrics, testId }: Props) {
  if (!metrics || metrics.signals_count === 0) {
    return (
      <div data-testid={testId} className="rounded-xl border p-4" style={{ borderColor: 'var(--lab-border)' }}>
        {title ? <h4 className="mb-2 text-sm font-semibold text-[var(--lab-cyan)]">{title}</h4> : null}
        <p className="text-sm text-[var(--lab-muted)]">Nessun segnale nel campione filtrato.</p>
      </div>
    )
  }

  return (
    <div
      data-testid={testId}
      className="rounded-xl border p-4"
      style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
    >
      {title ? <h4 className="mb-3 text-sm font-semibold text-[var(--lab-cyan)]">{title}</h4> : null}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-10">
        {METRIC_ROWS.map(({ key, label, format, colorize }) => {
          const raw = metrics[key]
          const value = typeof raw === 'number' ? raw : null
          const colorClass = colorize ? roiColorClass(key === 'roi_pct' ? value : metrics.roi_pct) : ''
          return (
            <div key={key} className="min-w-0">
              <div className="text-[10px] uppercase tracking-wide text-[var(--lab-muted)]">{label}</div>
              <div className={`text-sm font-semibold ${colorClass}`}>{format(value)}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

type RibbonProps = {
  real: HistoricalKpiSignalsOverall | null
  synthetic: HistoricalKpiSignalsOverall | null
  quoteType: 'real' | 'derived' | 'all' | undefined
}

export function HistoricalKpiMetricRibbon({ real, synthetic, quoteType }: RibbonProps) {
  const qt = quoteType ?? 'real'

  if (qt === 'all') {
    return (
      <section className="space-y-3" data-testid="historical-kpi-ribbon">
        <RibbonBlock title="Quote reali" metrics={real} testId="historical-kpi-ribbon-real" />
        <RibbonBlock
          title="Quote derivate — sintetiche"
          metrics={synthetic}
          testId="historical-kpi-ribbon-synthetic"
        />
      </section>
    )
  }

  const metrics = qt === 'derived' ? synthetic : real
  return (
    <section data-testid="historical-kpi-ribbon">
      <RibbonBlock metrics={metrics} />
    </section>
  )
}
