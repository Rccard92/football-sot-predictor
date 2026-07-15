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
  {
    key: 'candidate_rows_before_dedup',
    label: 'Candidati row-level',
    getValue: (s) => s.candidate_rows_before_dedup,
  },
  { key: 'unique_provider_fixtures', label: 'Fixture uniche', getValue: (s) => s.unique_provider_fixtures },
  {
    key: 'duplicates_removed_within_cohort',
    label: 'Duplicati rimossi',
    getValue: (s) => s.duplicates_removed_within_cohort,
  },
  { key: 'final', label: 'Righe finali', getValue: (s) => s.final_dataset_rows },
  { key: 'draws', label: 'Pareggi', getValue: (s) => s.draws },
  { key: 'rate', label: 'Draw rate %', getValue: (_s, drawRate) => `${drawRate.toFixed(2)}%` },
  { key: 'book', label: 'Con Book', getValue: (s) => s.rows_with_market_features },
  { key: 'leakage', label: 'Leakage safe', getValue: (s) => s.leakage_safe },
]

export function DrawCredibilityDatasetKpiCards({ summary, drawRatePct }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Coorte selezionata</h3>
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
