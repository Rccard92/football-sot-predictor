import {
  HEATMAP_COLUMNS,
  HEATMAP_SIGNAL_ROWS,
  type SignalsBucket,
  type SignalsSummaryResponse,
} from '../../../lib/cecchinoSignalsApi'
import { formatSuccessRate, heatmapCellClass } from './signalsHeatmapUtils'

type Props = {
  summary: SignalsSummaryResponse
}

function findCell(
  summary: SignalsSummaryResponse,
  signalGroup: string,
  sourceColumn: string,
) {
  return summary.by_signal_and_column.find(
    (row) => row.signal_group === signalGroup && row.source_column === sourceColumn,
  )
}

function sumRow(summary: SignalsSummaryResponse, signalGroup: string) {
  const cells = summary.by_signal_and_column.filter((row) => row.signal_group === signalGroup)
  const won = cells.reduce((acc, c) => acc + c.won, 0)
  const lost = cells.reduce((acc, c) => acc + c.lost, 0)
  const pending = cells.reduce((acc, c) => acc + c.pending, 0)
  const notEval = cells.reduce((acc, c) => acc + c.not_evaluable, 0)
  const activations = cells.reduce((acc, c) => acc + c.activations, 0)
  const settled = won + lost
  return {
    activations,
    settled,
    won,
    lost,
    pending,
    not_evaluable: notEval,
    success_rate: settled > 0 ? Math.round((won / settled) * 1000) / 10 : null,
  }
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
