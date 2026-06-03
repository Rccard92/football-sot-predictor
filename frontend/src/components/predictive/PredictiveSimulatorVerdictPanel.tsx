import type { V31CalibrationSimulator, V31PatternAnalysis } from '../../lib/api'
import {
  deriveMainIssue,
  fmtNum,
  labelFor,
  predictedHighCount,
  simStrategyByKey,
  strategyByKey,
} from './predictiveVerdictUtils'

type Props = {
  simulator: V31CalibrationSimulator | null
  pattern: V31PatternAnalysis | null
}

export function PredictiveSimulatorVerdictPanel({ simulator, pattern }: Props) {
  if (!simulator && !pattern) return null

  const dist = pattern?.summary.actual_sot_distribution
  const thresholds = pattern?.summary.dynamic_bucket_thresholds
  const best = simulator?.best_by
  const interp = simulator?.summary.model_interpretation

  const numericKey = best?.best_numeric_model?.strategy ?? interp?.best_numeric_model ?? 'v31_bias_corrected'
  const compromiseKey =
    best?.best_compromise_model?.strategy ?? interp?.best_compromise_model ?? 'v31_bias_dynamic_high_guard'
  const dynamicKey = best?.best_dynamic_model?.strategy ?? interp?.best_dynamic_model ?? 'v31_chaos_game'

  const numericSim = simStrategyByKey(simulator, numericKey)
  const compromiseSim = simStrategyByKey(simulator, compromiseKey)
  const dynamicPat = strategyByKey(pattern, dynamicKey)

  const fixturesCount = pattern?.summary.fixtures_count ?? simulator?.summary.fixtures_count

  return (
    <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h2 className="text-base font-semibold text-slate-900">Verdetto Pattern Analysis</h2>
        {dist ? (
          <p className="mt-1 text-xs text-slate-600">
            Dataset: {fixturesCount ?? dist.count} fixture · Actual avg: {fmtNum(dist.mean)} · p75:{' '}
            {fmtNum(thresholds?.p75)} · p90: {fmtNum(thresholds?.p90)} · p95: {fmtNum(thresholds?.p95)} ·
            Extreme actual:{' '}
            {String(strategyByKey(pattern, 'v31_bias_corrected')?.extreme_outlier_summary?.extreme_actual_count ?? '—')}
          </p>
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <VerdictCard
          title="Miglior precisione numerica"
          model={labelFor(simulator, numericKey)}
          lines={[
            `MAE ${fmtNum(numericSim?.predictive_metrics?.mae ?? numericSim?.regression_metrics?.mae)}`,
            `Bias ${fmtNum(numericSim?.predictive_metrics?.bias ?? numericSim?.regression_metrics?.bias)}`,
          ]}
          tone="emerald"
        />
        <VerdictCard
          title="Miglior compromesso attuale"
          model={labelFor(simulator, compromiseKey)}
          lines={[
            `MAE ${fmtNum(compromiseSim?.predictive_metrics?.mae ?? compromiseSim?.regression_metrics?.mae)}`,
            `Bias ${fmtNum(compromiseSim?.predictive_metrics?.bias ?? compromiseSim?.regression_metrics?.bias)}`,
            `Pred high ${predictedHighCount(strategyByKey(pattern, compromiseKey))}`,
          ]}
          tone="teal"
        />
        <VerdictCard
          title="Modello più dinamico"
          model={labelFor(simulator, dynamicKey)}
          lines={[
            `Pred high ${predictedHighCount(dynamicPat)}`,
            'Più varianza, più falsi positivi',
          ]}
          tone="violet"
        />
        <VerdictCard
          title="Problema principale"
          model=""
          lines={[deriveMainIssue(pattern)]}
          tone="amber"
        />
      </div>
    </section>
  )
}

function VerdictCard({
  title,
  model,
  lines,
  tone,
}: {
  title: string
  model: string
  lines: string[]
  tone: 'emerald' | 'teal' | 'violet' | 'amber'
}) {
  const colors = {
    emerald: 'border-emerald-200 bg-emerald-50/80',
    teal: 'border-teal-200 bg-teal-50/80',
    violet: 'border-violet-200 bg-violet-50/80',
    amber: 'border-amber-200 bg-amber-50/80',
  }
  return (
    <div className={`rounded-lg border p-3 text-xs ${colors[tone]}`}>
      <p className="font-medium text-slate-800">{title}</p>
      {model ? <p className="mt-1 font-semibold text-slate-900">{model}</p> : null}
      <ul className="mt-2 space-y-0.5 text-slate-700">
        {lines.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </div>
  )
}
