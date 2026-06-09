import { useMemo, useState } from 'react'
import type { SignalsSummaryResponse } from '../../lib/cecchinoSignalsApi'
import {
  formatOdds,
  formatSignalLabel,
  formatSuccessRate,
  formatTakenProfit,
  rankTopSignals,
  TOP_SORT_OPTIONS,
  type TopSortKey,
} from './signalsLabUtils'

type Props = {
  summary: SignalsSummaryResponse
  minSettled?: number
}

export function SignalsTopRankingLab({ summary, minSettled = 5 }: Props) {
  const [sortBy, setSortBy] = useState<TopSortKey>('taken_profit')

  const ranked = useMemo(
    () => rankTopSignals(summary, sortBy, minSettled, 10),
    [summary, sortBy, minSettled],
  )

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Top segnali</h3>
          <p className="mt-1 text-xs text-slate-500">Minimo {minSettled} segnali valutati</p>
        </div>
        <label className="text-xs text-slate-600">
          Ordina per{' '}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as TopSortKey)}
            className="ml-1 rounded-lg border border-slate-200 px-2 py-1 text-xs"
          >
            {TOP_SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-4 space-y-2">
        {ranked.length === 0 ? (
          <p className="text-sm text-slate-500">Nessun segnale con campione sufficiente.</p>
        ) : (
          ranked.map((row, idx) => (
            <div
              key={`${row.signal_group}-${row.source_column}`}
              className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-100 bg-gradient-to-r from-slate-50/80 to-white px-3 py-3 transition hover:border-indigo-100 hover:shadow-sm"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-800">
                {idx + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-slate-900">
                  {formatSignalLabel(row.signal_group, row.signal_label)} ·{' '}
                  {row.source_column.replace('EXCEL_', 'Excel ')}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {row.won}W / {row.lost}L · WR {formatSuccessRate(row.success_rate)}
                </p>
              </div>
              <div className="text-right text-xs tabular-nums">
                <p className="font-semibold text-emerald-800">
                  {formatTakenProfit(row.taken_profit_indicator)}
                </p>
                <p className="text-slate-500">
                  QP {formatOdds(row.avg_won_book_odds)} · QV {formatOdds(row.quota_void)}
                </p>
              </div>
              {row.settled < minSettled && (
                <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-800">
                  campione basso
                </span>
              )}
            </div>
          ))
        )}
      </div>
    </section>
  )
}
