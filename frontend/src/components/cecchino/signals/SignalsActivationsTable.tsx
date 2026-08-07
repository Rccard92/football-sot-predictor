import { Link } from 'react-router-dom'
import type { SignalActivationRow } from '../../../lib/cecchinoSignalsApi'
import {
  formatConsensusYesColumns,
  formatConsensusRatio,
} from '../../cecchino-lab/signalsLabUtils'
import { formatSignalLabel, formatTargetLabel, statusBadgeClass, statusLabel } from './signalsHeatmapUtils'

type Props = {
  items: SignalActivationRow[]
}

function QuotaBookCell({ row }: { row: SignalActivationRow }) {
  const isTaken = row.counts_in_avg_won_odds || (row.evaluation_status === 'won' && row.quota_book != null)
  const title = isTaken
    ? 'Quota presa — entra nella media prese'
    : row.evaluation_status === 'lost'
      ? 'La quota entra nella media prese solo se il segnale è WON'
      : undefined

  if (row.quota_book == null) {
    return <span className="text-slate-400">—</span>
  }

  return (
    <span
      title={title}
      className={
        isTaken
          ? 'inline-flex items-center gap-1 rounded-md border border-emerald-300 bg-emerald-50 px-1.5 py-0.5 font-medium text-emerald-900'
          : 'tabular-nums text-slate-700'
      }
    >
      {row.quota_book.toFixed(2)}
      {isTaken && <span className="text-[10px] font-normal text-emerald-700">presa</span>}
    </span>
  )
}

function shortColumnLabel(col: string): string {
  const raw = col.replace(/^EXCEL_/, '')
  if (raw === 'SCALA') return 'SCALA'
  return raw
}

function ConfirmationsCell({ row }: { row: SignalActivationRow }) {
  const group = row.signal_group
  const cols = formatConsensusYesColumns(row.consensus_yes_columns)
  const shortCols =
    cols === '—'
      ? '—'
      : cols
          .split(', ')
          .map((c) => shortColumnLabel(c.replace(/^Excel /, 'EXCEL_')))
          .join(' · ')

  if (group === 'HOME' || group === 'AWAY') {
    return (
      <div className="space-y-0.5" data-testid="confirmations-direct">
        <p className="text-xs font-medium text-slate-800">Segnale diretto</p>
        <p className="text-[11px] text-slate-600">D · SI</p>
        <span className="inline-flex rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-600">
          Single-formula
        </span>
      </div>
    )
  }

  if (group === 'DRAW_PT') {
    const ratio = formatConsensusRatio(row)
    return (
      <div className="space-y-0.5" data-testid="confirmations-draw-pt">
        <p className="text-xs font-medium text-slate-800">Derivato X</p>
        <p className="tabular-nums text-[11px] text-slate-700">{ratio} SI</p>
        {shortCols !== '—' && <p className="text-[10px] text-slate-500">{shortCols}</p>}
      </div>
    )
  }

  const yes = row.consensus_yes_count ?? 0
  const available = row.consensus_available_count
  const ratio =
    available != null ? `${yes} / ${available} SI` : formatConsensusRatio(row) + ' SI'
  const single = yes === 1 && (available == null || available > 1)

  return (
    <div
      className={`space-y-0.5 ${single ? 'text-amber-900' : 'text-slate-800'}`}
      data-testid="confirmations-ratio"
    >
      <p className={`tabular-nums text-xs font-medium ${single ? 'text-amber-800' : ''}`}>
        {ratio}
      </p>
      {shortCols !== '—' && (
        <p className={`text-[10px] ${single ? 'text-amber-700/80' : 'text-slate-500'}`}>
          {shortCols}
        </p>
      )}
      {single && (
        <p className="text-[10px] text-amber-700/90">Conferma singola</p>
      )}
    </div>
  )
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
              <th className="px-2 py-2 text-left">Conferme</th>
              <th className="px-2 py-2 text-left">Colonna</th>
              <th className="px-2 py-2 text-left">Target</th>
              <th className="px-2 py-2 text-left">Esito</th>
              <th className="px-2 py-2 text-left">FT</th>
              <th className="px-2 py-2 text-left">PT</th>
              <th className="px-2 py-2 text-left">Quota Book</th>
              <th className="px-2 py-2 text-left">Quota Cec.</th>
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
                <td className="px-2 py-2">
                  <ConfirmationsCell row={row} />
                </td>
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
                <td className="px-2 py-2">
                  <QuotaBookCell row={row} />
                </td>
                <td className="px-2 py-2 tabular-nums">{row.quota_cecchino ?? '—'}</td>
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
            <div className="mt-2">
              <ConfirmationsCell row={row} />
            </div>
            {row.evaluation_reason && (
              <p className="mt-1 text-[10px] text-slate-500">{row.evaluation_reason}</p>
            )}
            <p className="mt-2 text-xs text-slate-600">
              Quota book: <QuotaBookCell row={row} />
            </p>
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
