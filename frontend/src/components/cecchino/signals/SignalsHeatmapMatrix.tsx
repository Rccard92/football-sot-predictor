import {
  HEATMAP_COLUMNS,
  HEATMAP_SIGNAL_ROWS,
  type SignalsBucket,
  type SignalsSummaryResponse,
} from '../../../lib/cecchinoSignalsApi'
import {
  formatOdds,
  formatSuccessRate,
  formatVoidMargin,
  heatmapCellClass,
  mergeTakenOddsBuckets,
  voidMarginClass,
} from './signalsHeatmapUtils'

type Props = {
  summary: SignalsSummaryResponse
}

function findCell(
  summary: SignalsSummaryResponse,
  signalGroup: string,
  sourceColumn: string,
) {
  if (sourceColumn === 'SCALA' && (signalGroup === 'HOME' || signalGroup === 'AWAY')) {
    return undefined
  }
  return summary.by_signal_and_column.find(
    (row) => row.signal_group === signalGroup && row.source_column === sourceColumn,
  )
}

function sumRow(summary: SignalsSummaryResponse, signalGroup: string): SignalsBucket {
  const cells = summary.by_signal_and_column.filter((row) => row.signal_group === signalGroup)
  return mergeTakenOddsBuckets(cells) as SignalsBucket
}

function TakenOddsCompact({ bucket }: { bucket: SignalsBucket | Partial<SignalsBucket> | undefined }) {
  if (!bucket?.avg_won_book_odds && !bucket?.quota_void) return null
  return (
    <div className="mt-1 space-y-0.5 border-t border-slate-200/60 pt-1 text-[10px] leading-tight">
      {bucket.avg_won_book_odds != null && (
        <div className="tabular-nums">Quota prese: {formatOdds(bucket.avg_won_book_odds)}</div>
      )}
      {bucket.quota_void != null && (
        <div className="tabular-nums">Void: {formatOdds(bucket.quota_void)}</div>
      )}
      {bucket.void_margin != null && (
        <div className={`font-medium tabular-nums ${voidMarginClass(bucket.void_margin)}`}>
          {formatVoidMargin(bucket.void_margin)}
        </div>
      )}
    </div>
  )
}

function CellContent({ bucket }: { bucket: SignalsBucket | undefined }) {
  if (!bucket || bucket.activations === 0) {
    return <span className="text-slate-400">—</span>
  }
  return (
    <div className="space-y-0.5 text-center text-xs leading-tight">
      <div className="font-semibold tabular-nums">{bucket.activations}</div>
      {bucket.settled > 0 && (
        <div className="tabular-nums">
          {bucket.won}W / {bucket.lost}L
        </div>
      )}
      {bucket.settled >= 3 ? (
        <div className="font-medium">{formatSuccessRate(bucket.success_rate)}</div>
      ) : bucket.settled > 0 ? (
        <div className="text-[10px] text-slate-500">campione basso</div>
      ) : null}
      {bucket.pending > 0 && <div className="text-sky-700">+{bucket.pending} pending</div>}
      {bucket.not_evaluable > 0 && (
        <div className="text-slate-500">{bucket.not_evaluable} non valutabili</div>
      )}
      <TakenOddsCompact bucket={bucket} />
    </div>
  )
}

export function SignalsHeatmapMatrix({ summary }: Props) {
  return (
    <div className="space-y-4">
      <div className="hidden overflow-x-auto md:block">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="bg-slate-50 text-slate-600">
              <th className="border border-slate-200 px-3 py-2 text-left">Segnale</th>
              {HEATMAP_COLUMNS.map((col) => (
                <th key={col} className="border border-slate-200 px-3 py-2 text-center">
                  {col.replace('EXCEL_', 'Excel ')}
                </th>
              ))}
              <th className="border border-slate-200 px-3 py-2 text-center">Totale</th>
            </tr>
          </thead>
          <tbody>
            {HEATMAP_SIGNAL_ROWS.map((row) => {
              const total = sumRow(summary, row.group)
              return (
                <tr key={row.group}>
                  <td className="border border-slate-200 px-3 py-2 font-medium text-slate-800">
                    {row.label}
                  </td>
                  {HEATMAP_COLUMNS.map((col) => {
                    const bucket = findCell(summary, row.group, col)
                    return (
                      <td
                        key={col}
                        className={`border border-slate-200 px-2 py-2 ${heatmapCellClass(bucket)}`}
                      >
                        <CellContent bucket={bucket} />
                      </td>
                    )
                  })}
                  <td className={`border border-slate-200 px-2 py-2 ${heatmapCellClass(total)}`}>
                    <CellContent bucket={total} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-3 md:hidden">
        {HEATMAP_SIGNAL_ROWS.map((row) => (
          <article key={row.group} className="rounded-lg border border-slate-200 bg-white p-3">
            <h4 className="font-medium text-slate-800">{row.label}</h4>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {HEATMAP_COLUMNS.map((col) => {
                const bucket = findCell(summary, row.group, col)
                return (
                  <div
                    key={col}
                    className={`rounded-md border border-slate-100 p-2 ${heatmapCellClass(bucket)}`}
                  >
                    <p className="text-[10px] font-medium uppercase tracking-wide opacity-70">
                      {col.replace('EXCEL_', 'Excel ')}
                    </p>
                    <CellContent bucket={bucket} />
                  </div>
                )
              })}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
