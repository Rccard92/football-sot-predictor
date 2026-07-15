import { motion } from 'framer-motion'
import type { DrawCredibilityAuditSummary } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  summary: DrawCredibilityAuditSummary
  drawRatePct: number
}

const METRICS: Array<{
  key: keyof DrawCredibilityAuditSummary | 'draw_rate'
  label: string
  getValue: (s: DrawCredibilityAuditSummary, drawRate: number) => string | number
}> = [
  { key: 'total_fixtures', label: 'Fixture totali', getValue: (s) => s.total_fixtures },
  { key: 'finished_fixtures', label: 'Fixture concluse', getValue: (s) => s.finished_fixtures },
  { key: 'finished_with_result', label: 'Con risultato FT', getValue: (s) => s.finished_with_result },
  {
    key: 'usable_internal_research',
    label: 'Dataset interno utilizzabile',
    getValue: (s) => s.usable_internal_research,
  },
  {
    key: 'usable_market_comparison',
    label: 'Dataset con Book utilizzabile',
    getValue: (s) => s.usable_market_comparison,
  },
  {
    key: 'draw_rate',
    label: 'Frequenza pareggi %',
    getValue: (_s, drawRate) => `${drawRate.toFixed(2)}%`,
  },
]

export function DrawCredibilityResearchKpiCards({ summary, drawRatePct }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
      >
        {METRICS.map(({ key, label, getValue }) => (
          <div
            key={key}
            className="rounded-xl border border-slate-100 bg-gradient-to-br from-white to-slate-50/80 px-3 py-3 shadow-sm"
          >
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
              {getValue(summary, drawRatePct)}
            </p>
          </div>
        ))}
      </motion.div>
    </section>
  )
}
