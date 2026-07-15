import type { GlobalExclusionBreakdown } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  exclusions: GlobalExclusionBreakdown
}

export function DrawCredibilityGlobalExclusionsPanel({ exclusions }: Props) {
  if (exclusions.items.length === 0) {
    return null
  }

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Esclusioni globali prima del dataset</h3>
      <p className="mt-1 text-xs text-slate-500">
        Prima blocking reason per provider_fixture_id (mutuamente esclusiva).
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2 font-medium">Motivo</th>
              <th className="px-3 py-2 font-medium">Quantità</th>
              <th className="px-3 py-2 font-medium">% su uniche</th>
            </tr>
          </thead>
          <tbody>
            {exclusions.items.map((item) => (
              <tr key={item.reason} className="border-t border-slate-100">
                <td className="px-3 py-2">
                  <p className="font-medium text-slate-800">{item.label}</p>
                  <p className="text-[10px] text-slate-500">{item.reason}</p>
                </td>
                <td className="px-3 py-2 tabular-nums">{item.count}</td>
                <td className="px-3 py-2 tabular-nums">{item.pct_unique_fixtures.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
