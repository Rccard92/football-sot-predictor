import type { ComponentComparisonRow } from '../../lib/api'

const STATUS_CLASS: Record<string, string> = {
  overestimated: 'bg-rose-100 text-rose-900',
  underestimated: 'bg-orange-100 text-orange-900',
  aligned: 'bg-emerald-100 text-emerald-900',
  suspicious: 'bg-amber-200 text-amber-950',
  neutral: 'bg-slate-100 text-slate-700',
}

const fmt = (v?: number | null, digits?: number): string => {
  if (v == null || Number.isNaN(v)) return '-'
  return v.toFixed(digits ?? 2)
}

type Props = {
  rows: ComponentComparisonRow[]
  compact?: boolean
}

export function PredictiveComponentComparisonTable({ rows, compact }: Props) {
  if (!rows.length) {
    return <p className="text-xs text-slate-600">Nessun componente da mostrare.</p>
  }

  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table className="min-w-full text-left text-xs">
        <thead className="border-b border-slate-200 bg-slate-50 text-slate-700">
          <tr>
            {!compact ? <th className="px-2 py-2">Match</th> : null}
            {!compact ? <th className="px-2 py-2">G</th> : null}
            <th className="px-2 py-2">Squadra</th>
            <th className="px-2 py-2">Variabile</th>
            <th className="px-2 py-2">Predetto</th>
            <th className="px-2 py-2">Reale</th>
            <th className="px-2 py-2">Δ</th>
            <th className="px-2 py-2">Δ%</th>
            <th className="px-2 py-2">Peso</th>
            <th className="px-2 py-2">Contrib. pred</th>
            <th className="px-2 py-2">Contrib. actual*</th>
            <th className="px-2 py-2">Direzione</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const ui = row.ui_status ?? 'neutral'
            const cls = STATUS_CLASS[ui] ?? STATUS_CLASS.neutral
            const key = `${row.fixture_id}-${row.key}-${row.team_side}-${i}`
            return (
              <tr key={key} className="border-b border-slate-100 hover:bg-slate-50/50">
                {!compact ? <td className="px-2 py-2">{row.match}</td> : null}
                {!compact ? <td className="px-2 py-2">{row.round_number}</td> : null}
                <td className="px-2 py-2">{row.team}</td>
                <td className="px-2 py-2" title={row.macro_area_label}>
                  {row.label}
                </td>
                <td className="px-2 py-2">{fmt(row.predicted_value)}</td>
                <td className="px-2 py-2">{fmt(row.actual_value)}</td>
                <td className="px-2 py-2">{fmt(row.delta)}</td>
                <td className="px-2 py-2">
                  {row.delta_pct != null ? `${row.delta_pct.toFixed(0)}%` : '—'}
                </td>
                <td className="px-2 py-2">
                  {row.weight_pct != null ? `${row.weight_pct.toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-2">{fmt(row.predicted_contribution, 3)}</td>
                <td className="px-2 py-2">{fmt(row.actual_contribution_proxy, 3)}</td>
                <td className="px-2 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${cls}`}>
                    {row.error_direction ?? row.ui_status}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="px-2 py-1 text-[10px] text-slate-500">
        *Contributo actual è proxy diagnostico post-match, non usato in predizione.
      </p>
    </div>
  )
}
