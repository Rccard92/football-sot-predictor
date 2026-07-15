import type { DrawCredibilityCohortSummary } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  primary: DrawCredibilityCohortSummary
  sensitivity: DrawCredibilityCohortSummary
  market: DrawCredibilityCohortSummary
}

const ROWS: Array<{
  key: keyof DrawCredibilityCohortSummary
  label: string
}> = [
  { key: 'final_dataset_rows', label: 'Righe finali' },
  { key: 'draws', label: 'Pareggi' },
  { key: 'non_draws', label: 'Non pareggi' },
  { key: 'draw_rate_pct', label: 'Draw rate %' },
  { key: 'leakage_safe', label: 'Leakage safe' },
  { key: 'rows_with_market_features', label: 'Con Book' },
]

function fmt(key: keyof DrawCredibilityCohortSummary, value: number | undefined): string {
  const n = value ?? 0
  if (key === 'draw_rate_pct') return `${n.toFixed(2)}%`
  return String(n)
}

export function DrawCredibilityCohortComparisonTable({ primary, sensitivity, market }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Confronto coorti</h3>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2 font-medium">Metrica</th>
              <th className="px-3 py-2 font-medium">Primary</th>
              <th className="px-3 py-2 font-medium">Sensitivity</th>
              <th className="px-3 py-2 font-medium">Market</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(({ key, label }) => (
              <tr key={key} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium text-slate-700">{label}</td>
                <td className="px-3 py-2 tabular-nums">{fmt(key, primary[key])}</td>
                <td className="px-3 py-2 tabular-nums">{fmt(key, sensitivity[key])}</td>
                <td className="px-3 py-2 tabular-nums">{fmt(key, market[key])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
