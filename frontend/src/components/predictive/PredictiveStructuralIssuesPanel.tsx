import type { V31PatternAnalysis } from '../../lib/api'
import { fmtNum, strategyByKey } from './predictiveVerdictUtils'

type Props = {
  pattern: V31PatternAnalysis | null
}

const MODEL_KEYS = [
  { key: 'v31_bias_corrected', label: 'bias_corrected' },
  { key: 'v31_bias_dynamic_high_guard', label: 'dynamic_high_guard' },
  { key: 'v31_chaos_game', label: 'chaos_game' },
] as const

export function PredictiveStructuralIssuesPanel({ pattern }: Props) {
  if (!pattern) return null

  const biasHne = strategyByKey(pattern, 'v31_bias_corrected')?.high_total_non_extreme_summary as
    | { count_high_non_extreme?: number }
    | undefined
  const highCount = biasHne?.count_high_non_extreme ?? 0

  const extreme = Number(
    strategyByKey(pattern, 'v31_bias_corrected')?.extreme_outlier_summary?.extreme_actual_count ?? 0,
  )
  const p95 = pattern.summary.actual_sot_distribution?.p95

  return (
    <section className="space-y-4 rounded-lg border border-slate-200 bg-slate-50/50 p-4">
      <h2 className="text-sm font-semibold text-slate-900">Problemi strutturali rilevati</h2>

      <div className="rounded-lg border border-amber-200 bg-white p-3">
        <h3 className="text-xs font-medium text-amber-900">High non estreme</h3>
        <p className="mt-1 text-lg font-semibold text-slate-900">{highCount}</p>
        <p className="mt-2 text-xs text-slate-600">Sottostimate:</p>
        <ul className="mt-1 space-y-0.5 text-xs text-slate-800">
          {MODEL_KEYS.map(({ key, label }) => {
            const hne = strategyByKey(pattern, key)?.high_total_non_extreme_summary as
              | { count_high_non_extreme?: number; understated_count?: number }
              | undefined
            const total = hne?.count_high_non_extreme ?? highCount
            const under = hne?.understated_count ?? 0
            return (
              <li key={key}>
                {label}: {under}/{total}
              </li>
            )
          })}
        </ul>
        <p className="mt-2 text-xs text-slate-700">
          Il problema non sono solo gli outlier: anche molte partite alte ma non estreme vengono
          sottostimate.
        </p>
      </div>

      <div className="rounded-lg border border-violet-200 bg-white p-3">
        <h3 className="text-xs font-medium text-violet-900">Outlier estremi</h3>
        <p className="mt-1 text-lg font-semibold text-slate-900">{extreme}</p>
        <p className="mt-2 text-xs text-slate-700">
          Le partite oltre p95 ({fmtNum(p95)}) vanno studiate ma non inseguite con boost generalizzati.
        </p>
      </div>
    </section>
  )
}
