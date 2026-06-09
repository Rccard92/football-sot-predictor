import type { SignalActivationRow } from '../../lib/cecchinoSignalsApi'
import {
  formatSignalLabel,
  formatTargetLabel,
  statusBadgeClass,
  statusLabel,
} from './signalsLabUtils'

type Props = {
  items: SignalActivationRow[]
  onRowClick: (row: SignalActivationRow) => void
}

export function SignalsActivationsLab({ items, onRowClick }: Props) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-500">Nessun segnale nel periodo selezionato.</p>
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-100">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50/80 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Data</th>
            <th className="px-3 py-2">Match</th>
            <th className="px-3 py-2">Campionato</th>
            <th className="px-3 py-2">Segnale</th>
            <th className="px-3 py-2">Colonna</th>
            <th className="px-3 py-2">Target</th>
            <th className="px-3 py-2">Esito</th>
            <th className="px-3 py-2">Quota</th>
            <th className="px-3 py-2">FT</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((row) => (
            <tr
              key={row.id}
              onClick={() => onRowClick(row)}
              className="cursor-pointer transition hover:bg-indigo-50/50"
            >
              <td className="whitespace-nowrap px-3 py-2.5 text-slate-600">{row.scan_date}</td>
              <td className="px-3 py-2.5 font-medium text-slate-900">{row.match}</td>
              <td className="px-3 py-2.5 text-slate-600">{row.league_name ?? '—'}</td>
              <td className="px-3 py-2.5">{formatSignalLabel(row.signal_group, row.signal_label)}</td>
              <td className="px-3 py-2.5">{row.source_column.replace('EXCEL_', 'Excel ')}</td>
              <td className="px-3 py-2.5">{formatTargetLabel(row)}</td>
              <td className="px-3 py-2.5">
                <span
                  className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(row.evaluation_status)}`}
                >
                  {statusLabel(row.evaluation_status)}
                </span>
              </td>
              <td className="px-3 py-2.5 tabular-nums">
                {row.quota_book?.toFixed(2) ?? '—'}
                {row.counts_in_avg_won_odds && (
                  <span className="ml-1 text-[10px] text-emerald-700">presa</span>
                )}
              </td>
              <td className="px-3 py-2.5 tabular-nums">{row.ft_score ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
