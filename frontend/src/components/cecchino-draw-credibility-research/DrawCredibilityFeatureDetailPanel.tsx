import { useState } from 'react'

type NumericFeature = Record<string, unknown> & { feature?: string; bins?: Array<Record<string, unknown>> }

type Props = {
  features: NumericFeature[]
  primaryVsSensitivity: Array<Record<string, unknown>>
}

export function DrawCredibilityFeatureDetailPanel({ features, primaryVsSensitivity }: Props) {
  const [open, setOpen] = useState<string | null>(features[0]?.feature as string | null ?? null)
  const pvsMap = Object.fromEntries(
    primaryVsSensitivity.map((r) => [String(r.feature), r]),
  )

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Dettaglio variabili numeriche</h3>
      <div className="space-y-2">
        {features.slice(0, 12).map((f) => {
          const name = String(f.feature ?? '')
          const isOpen = open === name
          const bins = (f.bins as Array<Record<string, unknown>>) ?? []
          const pvs = pvsMap[name]
          return (
            <div key={name} className="rounded-lg border border-slate-100">
              <button
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-slate-800"
                onClick={() => setOpen(isOpen ? null : name)}
              >
                <span>{name}</span>
                <span className="text-xs text-slate-500">
                  AUC {String(f.discriminative_auc ?? '—')} · {String(f.trend ?? '')}
                </span>
              </button>
              {isOpen ? (
                <div className="border-t border-slate-100 px-3 py-2 text-xs">
                  {pvs ? (
                    <p className="mb-2 text-slate-600">
                      Primary vs Sensitivity: ΔAUC {String(pvs.auc_delta ?? '—')} ·{' '}
                      {String(pvs.stability_status ?? '')}
                    </p>
                  ) : null}
                  <table className="min-w-full">
                    <thead>
                      <tr className="text-slate-500">
                        <th className="py-1 pr-2">Bin</th>
                        <th className="py-1 pr-2">N</th>
                        <th className="py-1 pr-2">Draw %</th>
                        <th className="py-1">Lift pp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bins.map((b) => (
                        <tr key={String(b.index)}>
                          <td className="py-1 pr-2">{String(b.label)}</td>
                          <td className="py-1 pr-2 tabular-nums">{String(b.count)}</td>
                          <td className="py-1 pr-2 tabular-nums">
                            {typeof b.draw_rate_pct === 'number'
                              ? b.draw_rate_pct.toFixed(1)
                              : '—'}
                          </td>
                          <td className="py-1 tabular-nums">
                            {typeof b.lift_vs_baseline_pp === 'number'
                              ? b.lift_vs_baseline_pp.toFixed(1)
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </section>
  )
}
