import type { KpiHeatmapCell } from '../../lib/cecchinoKpiSignalsApi'
import { KPI_HEATMAP_ROWS, KPI_RATING_BUCKETS } from '../../lib/cecchinoKpiSignalsApi'

export type KpiHeatmapSelection = {
  selectionLabel: string
  ratingBucket: string
  cell: KpiHeatmapCell
}

type Props = {
  cells: KpiHeatmapCell[]
  onCellClick: (sel: KpiHeatmapSelection) => void
}

export function KpiSignalsHeatmap({ cells, onCellClick }: Props) {
  const map = new Map(cells.map((c) => [`${c.selection_label}|${c.rating_bucket}`, c]))
  return (
    <section className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-800">Heatmap pronostico × rating</h2>
      <table className="min-w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="border p-2 text-left">Pronostico</th>
            {KPI_RATING_BUCKETS.map((col) => (
              <th key={col} className="border p-2">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {KPI_HEATMAP_ROWS.map((row) => (
            <tr key={row}>
              <td className="border p-2 font-medium">{row}</td>
              {KPI_RATING_BUCKETS.map((col) => {
                const cell = map.get(`${row}|${col}`)
                if (!cell) {
                  return <td key={col} className="border p-2 text-slate-300">—</td>
                }
                return (
                  <td key={col} className="border p-1">
                    <button
                      type="button"
                      className="w-full rounded-lg bg-slate-50 p-2 text-left hover:bg-cyan-50"
                      onClick={() => onCellClick({ selectionLabel: row, ratingBucket: col, cell })}
                    >
                      <div className="font-semibold">{cell.activations}</div>
                      <div>{cell.won}/{cell.lost}</div>
                      <div>WR {cell.win_rate ?? '—'}%</div>
                      <div>P {cell.profit_units ?? '—'}</div>
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
