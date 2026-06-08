import { Link } from 'react-router-dom'
import type { SignalActivationRow } from '../../../lib/cecchinoSignalsApi'
import { formatSignalLabel, formatTargetLabel, statusBadgeClass, statusLabel } from './signalsHeatmapUtils'

type Props = {
  items: SignalActivationRow[]
}

export function SignalsActivationsTable({ items }: Props) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-500">Nessun segnale nel periodo selezionato.</p>
  }

  return (
    <div className="space-y-3">
      <div className="hidden overflow-x-auto md:block">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-2 py-2 text-left">Data</th>
              <th className="px-2 py-2 text-left">Match</th>
              <th className="px-2 py-2 text-left">Campionato</th>
              <th className="px-2 py-2 text-left">Segnale</th>
              <th className="px-2 py-2 text-left">Colonna</th>
              <th className="px-2 py-2 text-left">Target</th>
              <th className="px-2 py-2 text-left">Esito</th>
              <th className="px-2 py-2 text-left">FT</th>
              <th className="px-2 py-2 text-left">PT</th>
              <th className="px-2 py-2 text-left">Quota Cec.</th>
              <th className="px-2 py-2 text-left">Quota Book</th>
              <th className="px-2 py-2 text-left">Edge</th>
              <th className="px-2 py-2 text-left">Rating</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((row) => (
              <tr key={row.id} className="hover:bg-slate-50">
                <td className="px-2 py-2 whitespace-nowrap">{row.scan_date}</td>
                <td className="px-2 py-2">
                  <Link
                    to={`/cecchino-today?fixture=${row.today_fixture_id}&date=${row.scan_date}`}
                    className="text-sky-700 hover:underline"
                  >
                    {row.match}
                  </Link>
                </td>
                <td className="px-2 py-2">{row.league_name ?? '—'}</td>
                <td className="px-2 py-2">{formatSignalLabel(row.signal_group, row.signal_label)}</td>
                <td className="px-2 py-2">{row.source_column.replace('EXCEL_', 'Excel ')}</td>
                <td className="px-2 py-2">{formatTargetLabel(row)}</td>
                <td className="px-2 py-2">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(row.evaluation_status)}`}
                  >
                    {statusLabel(row.evaluation_status)}
                  </span>
                  {row.evaluation_reason && (
                    <p className="mt-1 text-[10px] text-slate-500">{row.evaluation_reason}</p>
                  )}
                </td>
                <td className="px-2 py-2 tabular-nums">{row.ft_score ?? '—'}</td>
                <td className="px-2 py-2 tabular-nums">{row.ht_score ?? '—'}</td>
                <td className="px-2 py-2 tabular-nums">{row.quota_cecchino ?? '—'}</td>
                <td className="px-2 py-2 tabular-nums">{row.quota_book ?? '—'}</td>
                <td className="px-2 py-2 tabular-nums">
                  {row.edge_pct != null ? `${row.edge_pct.toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-2 tabular-nums">{row.rating ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 md:hidden">
        {items.map((row) => (
          <article key={row.id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <Link
                to={`/cecchino-today?fixture=${row.today_fixture_id}&date=${row.scan_date}`}
                className="font-medium text-sky-700"
              >
                {row.match}
              </Link>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(row.evaluation_status)}`}
              >
                {statusLabel(row.evaluation_status)}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {row.scan_date} · {row.league_name ?? '—'}
            </p>
            <p className="mt-2">
              {formatSignalLabel(row.signal_group, row.signal_label)} ·{' '}
              {row.source_column.replace('EXCEL_', 'Excel ')} · {formatTargetLabel(row)}
            </p>
            {row.evaluation_reason && (
              <p className="mt-1 text-[10px] text-slate-500">{row.evaluation_reason}</p>
            )}
            <p className="mt-1 tabular-nums text-xs text-slate-600">
              FT {row.ft_score ?? '—'} · PT {row.ht_score ?? '—'} · Edge{' '}
              {row.edge_pct != null ? `${row.edge_pct.toFixed(1)}%` : '—'}
            </p>
          </article>
        ))}
      </div>
    </div>
  )
}
