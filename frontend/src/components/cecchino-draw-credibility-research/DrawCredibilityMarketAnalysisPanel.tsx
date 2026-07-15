import { useMemo, useState } from 'react'
import type {
  DrawCredibilityMarketAnalysis,
  DrawCredibilityRoiBlock,
} from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  market: DrawCredibilityMarketAnalysis
}

const COMPARISON_LABELS: Array<{ key: keyof DrawCredibilityMarketAnalysis['comparison']; label: string }> = [
  { key: 'rows_compared', label: 'Righe confrontate' },
  { key: 'delta_brier', label: 'Δ Brier' },
  { key: 'delta_brier_skill_score', label: 'Δ Brier skill' },
  { key: 'delta_log_loss', label: 'Δ Log loss' },
  { key: 'delta_auc', label: 'Δ AUC' },
  { key: 'delta_ece', label: 'Δ ECE' },
  { key: 'pct_cecchino_gt_book', label: '% Cecchino > Book' },
  { key: 'pct_cecchino_lt_book', label: '% Cecchino < Book' },
  { key: 'pct_approximately_equal_0_5pp', label: '% ≈ uguali (±0.5 pp)' },
  { key: 'mean_signed_deviation_x', label: 'Deviazione firmata media X' },
  { key: 'median_signed_deviation_x', label: 'Deviazione firmata mediana X' },
  { key: 'mean_absolute_deviation_x', label: 'MAD media X' },
  { key: 'median_absolute_deviation_x', label: 'MAD mediana X' },
]

const DIM_LABELS: Record<string, string> = {
  prob_x_norm: 'prob_x_norm (quintili)',
  prob_under: 'Under 2.5 (quintili)',
  deviation_x: 'deviation_x_pp (quintili)',
  x_rank: 'x_rank',
  dominant_sign_normalized: 'dominant_sign_normalized',
  conviction_class_candidate: 'conviction_class_candidate',
  f36_class_existing: 'f36_class_existing',
  hours_to_kickoff_class: 'hours_to_kickoff_class',
  pattern: 'Pattern candidati',
  market_global: 'Globale',
}

function fmt(n: unknown, digits = 4): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function dimensionOf(row: DrawCredibilityRoiBlock): string {
  const key = row.group_key ?? ''
  const idx = key.indexOf('__')
  if (idx > 0) return key.slice(0, idx)
  if (key.startsWith('pattern')) return 'pattern'
  return key || 'altro'
}

export function DrawCredibilityMarketAnalysisPanel({ market }: Props) {
  const comparison = market.comparison ?? {}
  const roi = market.roi ?? {}
  const warnings = [
    ...(market.methodological_warnings ?? []),
    ...(market.warnings ?? []),
  ]

  const dimensions = useMemo(() => {
    const rows = market.roi_breakdown ?? []
    return Array.from(new Set(rows.map(dimensionOf)))
  }, [market.roi_breakdown])

  const [dim, setDim] = useState<string>(dimensions[0] ?? '')
  const activeDim = dimensions.includes(dim) ? dim : dimensions[0] ?? ''
  const filtered = (market.roi_breakdown ?? []).filter((r) => dimensionOf(r) === activeDim)

  const boot = roi.bootstrap_roi_ci_95 as
    | { lower?: number; upper?: number; ci_lower?: number; ci_upper?: number }
    | null
    | undefined

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Analisi mercato (coorte Market)</h3>

      <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 text-xs font-medium text-amber-950">
        ROI storico teorico — non rappresenta una previsione futura.
      </p>

      <div className="space-y-5">
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
            Confronto Cecchino vs Book
          </h4>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {COMPARISON_LABELS.map(({ key, label }) => {
              const keyStr = String(key)
              const digits =
                keyStr.startsWith('pct_') ||
                keyStr.startsWith('mean_') ||
                keyStr.startsWith('median_')
                  ? 2
                  : 4
              return (
              <div key={keyStr} className="rounded-lg border border-slate-100 px-2 py-2 text-xs">
                <p className="text-[10px] uppercase text-slate-500">{label}</p>
                <p className="font-semibold tabular-nums text-slate-900">
                  {fmt(comparison[key], digits)}
                </p>
              </div>
              )
            })}
          </div>
        </div>

        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
            ROI globale
          </h4>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 text-xs">
            <div className="rounded-lg border border-slate-100 px-2 py-2">
              <p className="text-[10px] uppercase text-slate-500">Scommesse</p>
              <p className="font-semibold tabular-nums">{String(roi.bets ?? roi.count ?? 0)}</p>
            </div>
            <div className="rounded-lg border border-slate-100 px-2 py-2">
              <p className="text-[10px] uppercase text-slate-500">ROI %</p>
              <p className="font-semibold tabular-nums">
                {typeof roi.roi_pct === 'number' ? `${roi.roi_pct.toFixed(2)}%` : '—'}
              </p>
            </div>
            <div className="rounded-lg border border-slate-100 px-2 py-2">
              <p className="text-[10px] uppercase text-slate-500">Win rate</p>
              <p className="font-semibold tabular-nums">
                {typeof roi.win_rate_pct === 'number' ? `${roi.win_rate_pct.toFixed(1)}%` : '—'}
              </p>
            </div>
            <div className="rounded-lg border border-slate-100 px-2 py-2">
              <p className="text-[10px] uppercase text-slate-500">CI bootstrap ROI</p>
              <p className="font-semibold tabular-nums">
                {boot
                  ? `${fmt(boot.lower ?? boot.ci_lower, 2)}–${fmt(boot.upper ?? boot.ci_upper, 2)}`
                  : '—'}
              </p>
              <p className="text-[11px] text-slate-500">
                Affidabile: {roi.reliable ? 'Sì' : 'No'}
              </p>
            </div>
          </div>
        </div>

        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
            ROI per fasce
          </h4>
          {dimensions.length === 0 ? (
            <p className="text-xs text-slate-500">Nessun breakdown ROI disponibile.</p>
          ) : (
            <>
              <div className="mb-2">
                <select
                  className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                  value={activeDim}
                  onChange={(e) => setDim(e.target.value)}
                >
                  {dimensions.map((d) => (
                    <option key={d} value={d}>
                      {DIM_LABELS[d] ?? d}
                    </option>
                  ))}
                </select>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead className="border-b border-slate-200 text-slate-500">
                    <tr>
                      <th className="px-2 py-2 text-left">Fascia</th>
                      <th className="px-2 py-2 text-left">N</th>
                      <th className="px-2 py-2 text-left">ROI %</th>
                      <th className="px-2 py-2 text-left">Win %</th>
                      <th className="px-2 py-2 text-left">Affidabile</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((r) => (
                      <tr key={r.group_key ?? r.label} className="border-b border-slate-100">
                        <td className="px-2 py-1.5">{r.label ?? r.group_key}</td>
                        <td className="px-2 py-1.5 tabular-nums">{r.bets ?? r.count ?? 0}</td>
                        <td className="px-2 py-1.5 tabular-nums">
                          {typeof r.roi_pct === 'number' ? `${r.roi_pct.toFixed(2)}%` : '—'}
                        </td>
                        <td className="px-2 py-1.5 tabular-nums">
                          {typeof r.win_rate_pct === 'number'
                            ? `${r.win_rate_pct.toFixed(1)}%`
                            : '—'}
                        </td>
                        <td className="px-2 py-1.5">{r.reliable ? 'Sì' : 'No'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
            Avvertenze metodologiche
          </h4>
          {warnings.length === 0 ? (
            <p className="text-xs text-slate-500">Nessuna avvertenza aggiuntiva.</p>
          ) : (
            <ul className="list-disc space-y-1 pl-5 text-xs text-amber-900">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}
