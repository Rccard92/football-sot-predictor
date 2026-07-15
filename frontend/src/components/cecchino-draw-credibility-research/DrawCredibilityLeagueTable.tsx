import type { DrawCredibilityLeagueRow } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  rows: DrawCredibilityLeagueRow[]
}

export function DrawCredibilityLeagueTable({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Campionati</h2>
        <p className="mt-2 text-sm text-slate-500">Nessun dato per campionato.</p>
      </section>
    )
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Distribuzione per campionato</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Nazione</th>
              <th className="px-4 py-2 font-medium">Campionato</th>
              <th className="px-4 py-2 font-medium">Fixture</th>
              <th className="px-4 py-2 font-medium">Concluse</th>
              <th className="px-4 py-2 font-medium">Pareggi</th>
              <th className="px-4 py-2 font-medium">Util. interne</th>
              <th className="px-4 py-2 font-medium">Util. Book</th>
              <th className="px-4 py-2 font-medium">Copertura %</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={`${row.competition_id}-${row.league_name}`}
                className="border-t border-slate-100"
              >
                <td className="px-4 py-2 text-slate-700">{row.country_name || '—'}</td>
                <td className="px-4 py-2 text-slate-800">{row.league_name || '—'}</td>
                <td className="px-4 py-2 tabular-nums">{row.total}</td>
                <td className="px-4 py-2 tabular-nums">{row.finished}</td>
                <td className="px-4 py-2 tabular-nums">{row.draws}</td>
                <td className="px-4 py-2 tabular-nums">{row.internal_usable}</td>
                <td className="px-4 py-2 tabular-nums">{row.market_usable}</td>
                <td className="px-4 py-2 tabular-nums">{row.internal_coverage_pct.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
