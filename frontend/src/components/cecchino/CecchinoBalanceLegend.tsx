import {
  BALANCE_LEGEND_INTRO,
  BALANCE_LEGEND_NOTES,
  BALANCE_OPERATIONAL_LEGEND_RULES,
  type BalanceLegendSeverity,
  type BalanceOperationalLegendRow,
} from './balanceOperationalLegend'

function rowBg(severity: BalanceLegendSeverity): string {
  switch (severity) {
    case 'positive':
      return 'bg-emerald-50/80'
    case 'warning':
      return 'bg-amber-50/80'
    case 'negative':
      return 'bg-red-50/80'
    default:
      return 'bg-slate-50/80'
  }
}

function LegendRowCards({ rows }: { rows: BalanceOperationalLegendRow[] }) {
  return (
    <div className="space-y-2 md:hidden">
      {rows.map((row, idx) => (
        <article
          key={idx}
          className={`rounded-lg border border-slate-200 p-3 text-xs ${rowBg(row.severity)}`}
        >
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
            <dt className="text-slate-500">F36</dt>
            <dd className="font-medium text-slate-800">{row.f36}</dd>
            <dt className="text-slate-500">Segno dominante</dt>
            <dd className="font-medium text-slate-800">{row.dominantSide}</dd>
            <dt className="text-slate-500">Dominanza</dt>
            <dd className="font-medium text-slate-800">{row.dominance}</dd>
            <dt className="text-slate-500">Quota X</dt>
            <dd className="font-medium text-slate-800">{row.quotaX}</dd>
          </dl>
          <p className="mt-2 text-slate-800">{row.reading}</p>
        </article>
      ))}
    </div>
  )
}

function LegendTable({ rows }: { rows: BalanceOperationalLegendRow[] }) {
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-100 text-slate-600">
          <tr>
            <th className="px-2 py-2 text-left font-medium">F36</th>
            <th className="px-2 py-2 text-left font-medium">Segno dominante</th>
            <th className="px-2 py-2 text-left font-medium">Dominanza</th>
            <th className="px-2 py-2 text-left font-medium">Quota X</th>
            <th className="px-2 py-2 text-left font-medium">Lettura operativa</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, idx) => (
            <tr key={idx} className={rowBg(row.severity)}>
              <td className="px-2 py-2 whitespace-nowrap text-slate-800">{row.f36}</td>
              <td className="px-2 py-2 whitespace-nowrap text-slate-800">{row.dominantSide}</td>
              <td className="px-2 py-2 whitespace-nowrap text-slate-800">{row.dominance}</td>
              <td className="px-2 py-2 whitespace-nowrap text-slate-800">{row.quotaX}</td>
              <td className="px-2 py-2 text-slate-800">{row.reading}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CecchinoBalanceLegend() {
  return (
    <details className="rounded-lg border border-slate-200 bg-white text-sm">
      <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
        Legenda lettura operativa
      </summary>
      <div className="border-t border-slate-200 px-4 py-3 space-y-3">
        <p className="text-xs text-slate-600">{BALANCE_LEGEND_INTRO}</p>
        <LegendTable rows={BALANCE_OPERATIONAL_LEGEND_RULES} />
        <LegendRowCards rows={BALANCE_OPERATIONAL_LEGEND_RULES} />
        <div className="space-y-2 border-t border-slate-100 pt-3 text-xs text-slate-600">
          {BALANCE_LEGEND_NOTES.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      </div>
    </details>
  )
}
