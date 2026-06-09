import { useMemo, useState } from 'react'
import type { SignalsSummaryResponse } from '../../../lib/cecchinoSignalsApi'
import {
  formatOdds,
  formatSignalLabel,
  formatSuccessRate,
  formatTakenProfit,
  formatVoidMargin,
  voidMarginClass,
} from './signalsHeatmapUtils'

type Props = {
  summary: SignalsSummaryResponse
  minSettled?: number
}

type SortKey = 'taken_profit' | 'success_rate' | 'void_margin' | 'settled'

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: 'taken_profit', label: 'Rendimento prese' },
  { value: 'success_rate', label: 'Win Rate' },
  { value: 'void_margin', label: 'Margine Void' },
  { value: 'settled', label: 'Segnali valutati' },
]

export function SignalsTopRanking({ summary, minSettled = 5 }: Props) {
  const [sortBy, setSortBy] = useState<SortKey>('taken_profit')

  const ranked = useMemo(() => {
    const filtered = summary.by_signal_and_column.filter((row) => row.settled >= minSettled)
    const sorter = (a: (typeof filtered)[0], b: (typeof filtered)[0]) => {
      switch (sortBy) {
        case 'success_rate':
          return (b.success_rate ?? 0) - (a.success_rate ?? 0)
        case 'void_margin':
          return (b.void_margin ?? -999) - (a.void_margin ?? -999)
        case 'settled':
          return b.settled - a.settled
        case 'taken_profit':
        default:
          return (b.taken_profit_indicator ?? -999) - (a.taken_profit_indicator ?? -999)
      }
    }
    return [...filtered].sort(sorter).slice(0, 10)
  }, [summary.by_signal_and_column, minSettled, sortBy])

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Top segnali</h3>
          <p className="mt-1 text-xs text-slate-500">Minimo {minSettled} segnali valutati</p>
        </div>
        <label className="text-xs text-slate-600">
          Ordina per{' '}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="ml-1 rounded border border-slate-300 px-2 py-1 text-xs"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {ranked.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">Nessun segnale con campione sufficiente.</p>
      ) : (
        <ol className="mt-3 space-y-2">
          {ranked.map((row) => (
            <li
              key={`${row.signal_group}-${row.source_column}`}
              className="rounded-md bg-slate-50 px-3 py-2 text-sm"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium text-slate-800">
                  {formatSignalLabel(row.signal_group, row.signal_label)} /{' '}
                  {row.source_column.replace('EXCEL_', 'Excel ')}
                </span>
                <span className="tabular-nums text-slate-700">
                  {formatSuccessRate(row.success_rate)} — {row.won}/{row.settled}
                </span>
              </div>
              <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs tabular-nums text-slate-600 sm:grid-cols-4">
                <div>
                  <dt className="text-slate-400">Quota prese</dt>
                  <dd>{formatOdds(row.avg_won_book_odds)}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">Void</dt>
                  <dd>{formatOdds(row.quota_void)}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">Margine</dt>
                  <dd className={voidMarginClass(row.void_margin)}>
                    {formatVoidMargin(row.void_margin)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">Rendimento</dt>
                  <dd>{formatTakenProfit(row.taken_profit_indicator)}</dd>
                </div>
              </dl>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
