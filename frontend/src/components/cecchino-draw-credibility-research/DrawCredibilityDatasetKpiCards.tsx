import { motion } from 'framer-motion'
import type { DrawCredibilityCohortSummary } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  summary: DrawCredibilityCohortSummary
  drawRatePct: number
}

const METRICS: Array<{
  key: string
  label: string
  getValue: (s: DrawCredibilityCohortSummary, drawRate: number) => string | number
}> = [
  { key: 'raw', label: 'Righe raw', getValue: (s) => s.raw_rows_found },
  { key: 'unique', label: 'Fixture uniche', getValue: (s) => s.unique_provider_fixtures },
  { key: 'dup', label: 'Duplicati collassati', getValue: (s) => s.duplicate_rows_collapsed },
  { key: 'leakage', label: 'Leakage safe', getValue: (s) => s.leakage_safe },
  { key: 'final', label: 'Righe finali', getValue: (s) => s.final_dataset_rows },
  { key: 'draws', label: 'Pareggi', getValue: (s) => s.draws },
  { key: 'rate', label: 'Draw rate %', getValue: (_s, drawRate) => `${drawRate.toFixed(2)}%` },
  { key: 'book', label: 'Con Book', getValue: (s) => s.rows_with_market_features },
]

export function DrawCredibilityDatasetKpiCards({ summary, drawRatePct }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8"
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
