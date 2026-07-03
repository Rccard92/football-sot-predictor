import type { KpiSignalActivationRow } from '../../lib/cecchinoKpiSignalsApi'
import { formatOdds } from '../cecchino-lab/signalsLabUtils'

type Props = {
  rows: KpiSignalActivationRow[]
  onRowClick: (row: KpiSignalActivationRow) => void
}

export function KpiSignalsTable({ rows, onRowClick }: Props) {
  return (
    <section className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
      <h2 className="border-b px-4 py-3 text-sm font-semibold text-slate-800">Dettaglio segnali KPI</h2>
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="px-3 py-2 text-left">Data</th>
            <th className="px-3 py-2 text-left">Partita</th>
            <th className="px-3 py-2 text-left">Campionato</th>
            <th className="px-3 py-2 text-left">Pronostico</th>
            <th className="px-3 py-2 text-left">Rating</th>
            <th className="px-3 py-2 text-left">Bucket</th>
            <th className="px-3 py-2 text-left">Quota Book</th>
            <th className="px-3 py-2 text-left">Edge %</th>
            <th className="px-3 py-2 text-left">PT</th>
            <th className="px-3 py-2 text-left">FT</th>
            <th className="px-3 py-2 text-left">Esito</th>
            <th className="px-3 py-2 text-left">Profitto</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="cursor-pointer border-t hover:bg-cyan-50/40" onClick={() => onRowClick(row)}>
              <td className="px-3 py-2">{row.scan_date}</td>
              <td className="px-3 py-2">{row.home_team_name} vs {row.away_team_name}</td>
              <td className="px-3 py-2">{row.league_name}</td>
              <td className="px-3 py-2 font-medium">{row.selection_label}</td>
              <td className="px-3 py-2">{row.rating_score}</td>
              <td className="px-3 py-2">{row.rating_bucket}</td>
              <td className="px-3 py-2">{formatOdds(row.quota_book)}</td>
              <td className="px-3 py-2">{row.edge_pct ?? '—'}</td>
              <td className="px-3 py-2">{row.result_home_ht ?? '—'}:{row.result_away_ht ?? '—'}</td>
              <td className="px-3 py-2">{row.result_home_ft ?? '—'}:{row.result_away_ft ?? '—'}</td>
              <td className="px-3 py-2">{row.evaluation_status}</td>
              <td className="px-3 py-2">{row.profit_units ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
