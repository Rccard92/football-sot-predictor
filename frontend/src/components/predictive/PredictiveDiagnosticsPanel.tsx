import type { V31PatternAnalysis } from '../../lib/api'
import { fmtNum, predictedHighCount, strategyByKey } from './predictiveVerdictUtils'

type Props = {
  pattern: V31PatternAnalysis | null
}

export function PredictiveDiagnosticsPanel({ pattern }: Props) {
  if (!pattern) return null

  const hybrid = strategyByKey(pattern, 'v31_bias_dynamic_high_guard')
  const chaos = strategyByKey(pattern, 'v31_chaos_game')
  const hd = hybrid?.hybrid_debug as Record<string, unknown> | undefined
  const clusters = pattern.summary.top3_cluster_summary?.counts ?? {}

  const chaosBad =
    (chaos?.loss_quality_summary?.counts?.BAD_LOSS_OVERESTIMATION as number | undefined) ??
    (chaos?.losing_patterns?.categories?.BAD_LOSS_OVERESTIMATION?.count as number | undefined) ??
    0

  const falseHigh =
    (chaos?.losing_patterns?.special_categories?.false_high_prediction?.count as number | undefined) ?? 0

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="rounded-lg border border-teal-200 bg-teal-50/40 p-4 text-xs">
        <h3 className="font-semibold text-teal-900">v31_bias_dynamic_high_guard</h3>
        <ul className="mt-2 space-y-1 text-slate-800">
          <li>boosted_fixtures_count: {String(hd?.boosted_fixtures_count ?? '—')}</li>
          <li>avg_boost_applied: {fmtNum(hd?.avg_boost_applied as number | undefined, 4)}</li>
          <li>max_boost_applied: {fmtNum(hd?.max_boost_applied as number | undefined, 2)}</li>
          <li>guardrail_blocked_count: {String(hd?.guardrail_blocked_count ?? 0)}</li>
          <li>dynamic_guard_improves_bias: {clusters.dynamic_guard_improves_bias ?? 0}</li>
          <li>dynamic_guard_worsens_bias: {clusters.dynamic_guard_worsens_bias ?? 0}</li>
        </ul>
        <p className="mt-3 text-slate-700">
          Il boost dinamico è attivo, ma oggi peggiora la baseline più spesso di quanto la migliori. I
          guardrail non stanno bloccando nessuna partita: vanno resi più selettivi.
        </p>
      </div>

      <div className="rounded-lg border border-violet-200 bg-violet-50/40 p-4 text-xs">
        <h3 className="font-semibold text-violet-900">v31_chaos_game</h3>
        <ul className="mt-2 space-y-1 text-slate-800">
          <li>predicted high: {predictedHighCount(chaos)}</li>
          <li>chaos catches high non extreme: {clusters.chaos_catches_high_non_extreme ?? 0}</li>
          <li>chaos false positive: {clusters.chaos_false_positive ?? falseHigh}</li>
          <li>bad loss overestimation: {chaosBad}</li>
        </ul>
        <p className="mt-3 text-slate-700">
          Chaos game è utile per aumentare la varianza e studiare partite alte, ma non è pronto come
          modello finale perché produce troppi falsi positivi.
        </p>
      </div>
    </div>
  )
}

export function PredictiveNextDirectionPanel() {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="text-sm font-semibold text-slate-900">Prossima direzione modello</h2>
      <p className="mt-2 text-xs leading-relaxed text-slate-700">
        La base più solida resta v31_bias_corrected. La nuova direzione è costruire un candidato ibrido
        che usi la stabilità del bias corrected, recuperi alcuni segnali utili da chaos_game, ma
        introduca guardrail più severi per evitare false high prediction.
      </p>
    </section>
  )
}

export function PredictiveAuditPanel({ pattern }: { pattern: V31PatternAnalysis | null }) {
  const ok = pattern?.audit && Object.values(pattern.audit).every((v) => v === true)
  return (
    <section className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4 text-xs">
      <div className="flex items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 font-medium ${ok ? 'bg-emerald-200 text-emerald-900' : 'bg-rose-200 text-rose-900'}`}
        >
          Anti-leakage: {ok ? 'OK' : 'Verifica'}
        </span>
      </div>
      <ul className="mt-2 list-inside list-disc space-y-0.5 text-slate-700">
        <li>actual_total_sot usato solo post-match</li>
        <li>bucket actual usato solo post-match</li>
        <li>win_quality solo diagnostica</li>
        <li>pattern analysis non modifica i pesi automaticamente</li>
        <li>betting phase disabled</li>
      </ul>
    </section>
  )
}
