import { motion } from 'framer-motion'
import type { HistoricalRunDashboardOverview } from '../../../lib/cecchinoLabApi'

type Props = { overview: HistoricalRunDashboardOverview }

export function HistoricalRunV1Pulse({ overview }: Props) {
  const k = overview.kpis
  const cards = [
    { label: 'Eleggibili', value: k.matches_eligible },
    { label: 'Copertura', value: k.coverage_pct != null ? `${k.coverage_pct}%` : '—' },
    { label: 'Valutazioni mercato', value: k.market_evaluations },
    { label: 'Quote reali', value: k.markets_with_real_quote },
    { label: 'Quote derivate', value: k.markets_with_derived_quote },
    { label: 'Segnali attivati', value: k.signals_activated },
    { label: 'Campionati', value: k.competitions_represented },
    { label: 'Miglior calibrazione', value: k.best_calibrated_market ?? '—' },
    { label: 'Peggior calibrazione', value: k.worst_calibrated_market ?? '—' },
    { label: 'Miglior ROI reale*', value: k.best_market_by_real_roi ?? '—' },
    { label: 'Peggior ROI reale*', value: k.worst_market_by_real_roi ?? '—' },
  ]

  return (
    <section>
      <h3 className="mb-3 text-lg font-semibold">V1 Pulse</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Prestazioni osservate. *ROI reale solo con sample minimo. Mercati indipendenti non sommati.
      </p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {cards.map((c, i) => (
          <motion.div
            key={c.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03 }}
            className="rounded-xl border p-3"
            style={{
              borderColor: 'var(--lab-border)',
              background: 'linear-gradient(160deg, rgba(46,230,255,0.06), var(--lab-surface))',
            }}
          >
            <div className="text-[11px] uppercase tracking-wide text-[var(--lab-muted)]">
              {c.label}
            </div>
            <div className="mt-1 text-xl font-semibold text-[var(--lab-cyan)]">
              {c.value == null ? '—' : String(c.value)}
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
