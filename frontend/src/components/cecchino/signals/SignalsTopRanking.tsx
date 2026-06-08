import type { SignalsSummaryResponse } from '../../../lib/cecchinoSignalsApi'
import { formatSignalLabel, formatSuccessRate } from './signalsHeatmapUtils'

type Props = {
  summary: SignalsSummaryResponse
  minSettled?: number
}

export function SignalsTopRanking({ summary, minSettled = 5 }: Props) {
  const ranked = [...summary.by_signal_and_column]
    .filter((row) => row.settled >= minSettled)
    .sort((a, b) => (b.success_rate ?? 0) - (a.success_rate ?? 0))
    .slice(0, 10)

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-800">Top segnali</h3>
      <p className="mt-1 text-xs text-slate-500">Minimo {minSettled} segnali valutati</p>
      {ranked.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">Nessun segnale con campione sufficiente.</p>
      ) : (
        <ol className="mt-3 space-y-2">
          {ranked.map((row) => (
            <li
              key={`${row.signal_group}-${row.source_column}`}
              className="flex flex-wrap items-baseline justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm"
            >
              <span className="font-medium text-slate-800">
                {formatSignalLabel(row.signal_group, row.signal_label)} /{' '}
                {row.source_column.replace('EXCEL_', 'Excel ')}
              </span>
              <span className="tabular-nums text-slate-700">
                {formatSuccessRate(row.success_rate)} — {row.won}/{row.settled} — {row.activations}{' '}
                attivazioni
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
