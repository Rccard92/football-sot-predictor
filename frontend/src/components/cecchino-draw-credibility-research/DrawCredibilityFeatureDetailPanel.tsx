import { useMemo, useState } from 'react'

type FeatureBin = Record<string, unknown> & {
  index?: number
  label?: string
  count?: number
  draw_rate_pct?: number
  lift_vs_baseline_pp?: number
  wilson_ci_95?: { lower_pct?: number | null; upper_pct?: number | null }
  reliable?: boolean
}

type NumericFeature = Record<string, unknown> & {
  feature?: string
  bins?: FeatureBin[]
  directional_auc?: number | null
  discriminative_auc?: number | null
  pearson?: number | null
  spearman?: number | null
  trend?: string
  trend_diagnostics?: Record<string, unknown>
  bootstrap?: Record<string, unknown> | null
  reliability_status?: string
  feature_family?: string | null
  boundaries?: number[]
  boundary_source?: string
}

type Props = {
  features: NumericFeature[]
  sensitivityFeatures?: NumericFeature[]
  primaryVsSensitivity: Array<Record<string, unknown>>
}

const FEATURE_LABELS_IT: Record<string, string> = {
  prob_x_norm: 'Probabilità X normalizzata',
  quota_cecchino_x: 'Quota Cecchino X',
  x_vs_best_lateral_pp: 'X vs migliore laterale (pp)',
  x_vs_second_probability_pp: 'X vs seconda probabilità (pp)',
  f36_abs: 'F36 assoluto',
  f36_score_existing: 'Score F36 esistente',
  dominance_pp: 'Dominanza (pp)',
  dominance_normalized_pp: 'Dominanza normalizzata (pp)',
  conviction_index_candidate: 'Indice di convinzione (candidato)',
  x_directional_conviction_candidate: 'Convinzione direzionale X (candidato)',
  probability_gap_1_2_pp: 'Gap probabilità 1–2 (pp)',
  probability_balance_index: 'Indice di equilibrio probabilità',
  gap_coherence_index_candidate: 'Indice coerenza gap (candidato)',
  prob_under_2_5_cecchino_pct: 'Prob. Under 2.5 Cecchino (%)',
  under_minus_over_pp: 'Under − Over (pp)',
  under_strength_pp: 'Forza Under (pp)',
  hours_to_kickoff: "Ore al calcio d'inizio",
}

function labelOf(name: string): string {
  return FEATURE_LABELS_IT[name] ?? name
}

function fmt(n: unknown, digits = 3): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function wilsonTxt(ci: FeatureBin['wilson_ci_95']): string {
  if (!ci || typeof ci.lower_pct !== 'number' || typeof ci.upper_pct !== 'number') return '—'
  return `${ci.lower_pct.toFixed(1)}–${ci.upper_pct.toFixed(1)}%`
}

function BinsTable({ bins, title }: { bins: FeatureBin[]; title: string }) {
  if (bins.length === 0) {
    return <p className="text-slate-500">{title}: nessun bin disponibile.</p>
  }
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-violet-700">{title}</p>
      <table className="min-w-full">
        <thead>
          <tr className="text-slate-500">
            <th className="py-1 pr-2 text-left">Bin</th>
            <th className="py-1 pr-2 text-left">N</th>
            <th className="py-1 pr-2 text-left">Draw %</th>
            <th className="py-1 pr-2 text-left">Wilson CI</th>
            <th className="py-1 pr-2 text-left">Lift pp</th>
            <th className="py-1 text-left">Affidabile</th>
          </tr>
        </thead>
        <tbody>
          {bins.map((b) => (
            <tr key={String(b.index ?? b.label)} className="border-t border-slate-50">
              <td className="py-1 pr-2">{String(b.label ?? '—')}</td>
              <td className="py-1 pr-2 tabular-nums">{String(b.count ?? '—')}</td>
              <td className="py-1 pr-2 tabular-nums">{fmt(b.draw_rate_pct, 1)}</td>
              <td className="py-1 pr-2 tabular-nums">{wilsonTxt(b.wilson_ci_95)}</td>
              <td className="py-1 pr-2 tabular-nums">{fmt(b.lift_vs_baseline_pp, 1)}</td>
              <td className="py-1">{b.reliable ? 'Sì' : 'No'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DrawCredibilityFeatureDetailPanel({
  features,
  sensitivityFeatures = [],
  primaryVsSensitivity,
}: Props) {
  const [open, setOpen] = useState<string | null>((features[0]?.feature as string | null) ?? null)

  const sensMap = useMemo(
    () => Object.fromEntries(sensitivityFeatures.map((r) => [String(r.feature), r])),
    [sensitivityFeatures],
  )
  const pvsMap = useMemo(
    () => Object.fromEntries(primaryVsSensitivity.map((r) => [String(r.feature), r])),
    [primaryVsSensitivity],
  )

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Dettaglio variabili numeriche</h3>
      <div className="space-y-2">
        {features.slice(0, 20).map((f) => {
          const name = String(f.feature ?? '')
          const isOpen = open === name
          const primaryBins = f.bins ?? []
          const sens = sensMap[name]
          const sensBins = (sens?.bins as FeatureBin[] | undefined) ?? []
          const pvs = pvsMap[name]
          const boot = f.bootstrap
          const family = (f.feature_family as string | null | undefined) ?? null
          const trendDiag = f.trend_diagnostics

          return (
            <div key={name} className="rounded-lg border border-slate-100">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium text-slate-800"
                onClick={() => setOpen(isOpen ? null : name)}
              >
                <span className="min-w-0">
                  <span className="block truncate">{labelOf(name)}</span>
                  <span className="block truncate text-[11px] font-normal text-slate-500">{name}</span>
                </span>
                <span className="shrink-0 text-xs text-slate-500">
                  disc {fmt(f.discriminative_auc)} · {String(f.trend ?? '')}
                </span>
              </button>
              {isOpen ? (
                <div className="space-y-3 border-t border-slate-100 px-3 py-3 text-xs">
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-slate-600">
                    <span>Famiglia: {family ?? '—'}</span>
                    <span>Reliability: {String(f.reliability_status ?? '—')}</span>
                    <span>Stabilità Prim/Sens: {String(pvs?.stability_status ?? '—')}</span>
                    <span>Boundary: {String(f.boundary_source ?? '—')}</span>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    <p>
                      AUC dir. {fmt(f.directional_auc)} · disc. {fmt(f.discriminative_auc)}
                    </p>
                    <p>
                      Pearson {fmt(f.pearson)} · Spearman {fmt(f.spearman)}
                    </p>
                    <p>
                      Bootstrap dir CI:{' '}
                      {fmt(boot?.directional_auc_ci_lower)}–{fmt(boot?.directional_auc_ci_upper)}
                    </p>
                    <p>
                      Bootstrap disc CI:{' '}
                      {fmt(boot?.discriminative_auc_ci_lower)}–{fmt(boot?.discriminative_auc_ci_upper)}
                    </p>
                  </div>
                  {trendDiag ? (
                    <p className="rounded-lg border border-violet-100 bg-violet-50/40 px-2 py-1.5 text-violet-900">
                      Trend diagnostics:{' '}
                      {Object.entries(trendDiag)
                        .map(([k, v]) => `${k}=${String(v)}`)
                        .join(' · ')}
                    </p>
                  ) : null}
                  {pvs ? (
                    <p className="text-slate-600">
                      Primary vs Sensitivity: ΔAUC dir{' '}
                      {fmt(pvs.directional_auc_delta ?? pvs.auc_delta)} · stabilità{' '}
                      {String(pvs.stability_status ?? '—')}
                    </p>
                  ) : null}
                  <BinsTable bins={primaryBins} title="Bin Primary" />
                  <BinsTable bins={sensBins} title="Bin Sensitivity (stessi boundary Primary)" />
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </section>
  )
}
