import type { KpiSignalActivationRow } from '../../lib/cecchinoKpiSignalsApi'
import { formatOdds } from '../cecchino-lab/signalsLabUtils'
import {
  formatKpiProfit,
  kpiStatusBadgeClass,
  kpiStatusLabel,
  profitTextClass,
} from './kpiSignalsLabUtils'

type Props = {
  rows: KpiSignalActivationRow[]
  onRowClick: (row: KpiSignalActivationRow) => void
}

export function KpiSignalsActivationsLab({ rows, onRowClick }: Props) {
  if (rows.length === 0) {
    return (
      <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <p className="text-sm text-slate-500">Nessun segnale KPI nel periodo selezionato.</p>
      </section>
    )
  }

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-800">Dettaglio segnali KPI</h2>
      <div className="overflow-x-auto rounded-xl border border-slate-100">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Data</th>
              <th className="px-3 py-2">Partita</th>
              <th className="px-3 py-2">Campionato</th>
              <th className="px-3 py-2">Pronostico</th>
              <th className="px-3 py-2">Rating</th>
              <th className="px-3 py-2">Bucket</th>
              <th className="px-3 py-2">Quota Book</th>
              <th className="px-3 py-2">Quota Cecchino</th>
              <th className="px-3 py-2">Edge %</th>
              <th className="px-3 py-2">PT</th>
              <th className="px-3 py-2">FT</th>
              <th className="px-3 py-2">Esito</th>
              <th className="px-3 py-2">Profitto</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onRowClick(row)}
                className="cursor-pointer transition hover:bg-cyan-50/50"
              >
                <td className="whitespace-nowrap px-3 py-2.5 text-slate-600">{row.scan_date}</td>
                <td className="px-3 py-2.5 font-medium text-slate-900">
                  {row.home_team_name} vs {row.away_team_name}
                </td>
                <td className="px-3 py-2.5 text-slate-600">{row.league_name ?? '—'}</td>
                <td className="px-3 py-2.5 font-medium">{row.selection_label}</td>
                <td className="px-3 py-2.5 tabular-nums">{row.rating_score}</td>
                <td className="px-3 py-2.5">{row.rating_bucket}</td>
                <td className="px-3 py-2.5 tabular-nums">{formatOdds(row.quota_book)}</td>
                <td className="px-3 py-2.5 tabular-nums">{formatOdds(row.quota_cecchino)}</td>
                <td className="px-3 py-2.5 tabular-nums">{row.edge_pct ?? '—'}</td>
                <td className="px-3 py-2.5 tabular-nums">
                  {row.result_home_ht ?? '—'}:{row.result_away_ht ?? '—'}
                </td>
                <td className="px-3 py-2.5 tabular-nums">
                  {row.result_home_ft ?? '—'}:{row.result_away_ft ?? '—'}
                </td>
                <td className="px-3 py-2.5">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${kpiStatusBadgeClass(row.evaluation_status)}`}
                  >
                    {kpiStatusLabel(row.evaluation_status)}
                  </span>
                </td>
                <td className={`px-3 py-2.5 tabular-nums font-semibold ${profitTextClass(row.profit_units)}`}>
                  {formatKpiProfit(row.profit_units)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
