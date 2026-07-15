import type { DrawCredibilityVersionRow } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  distribution: Record<string, DrawCredibilityVersionRow[]>
}

const LABELS: Record<string, string> = {
  cecchino_output: 'Cecchino output',
  balance_analysis: 'Balance analysis',
  goal_markets: 'Goal markets',
  kpi_panel: 'KPI panel',
  payload_structure: 'Payload structure',
}

export function DrawCredibilityVersionTable({ distribution }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Distribuzione versioni</h3>
      <div className="mt-3 space-y-4">
        {Object.entries(distribution).map(([key, rows]) => (
          <div key={key}>
            <p className="text-xs font-medium text-slate-600">{LABELS[key] ?? key}</p>
            <div className="mt-1 overflow-x-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-2 py-1.5 font-medium">Versione</th>
                    <th className="px-2 py-1.5 font-medium">Count</th>
                    <th className="px-2 py-1.5 font-medium">%</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={`${key}-${row.version}`} className="border-t border-slate-100">
                      <td className="px-2 py-1.5 font-mono text-[11px]">{row.version}</td>
                      <td className="px-2 py-1.5 tabular-nums">{row.count}</td>
                      <td className="px-2 py-1.5 tabular-nums">{row.pct.toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
