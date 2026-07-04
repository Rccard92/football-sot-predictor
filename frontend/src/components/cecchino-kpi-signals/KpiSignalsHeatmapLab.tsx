import type { KpiHeatmapCell } from '../../lib/cecchinoKpiSignalsApi'
import { KPI_HEATMAP_ROWS, KPI_RATING_BUCKETS } from '../../lib/cecchinoKpiSignalsApi'
import { KpiCellLab } from './KpiCellLab'

export type KpiHeatmapSelection = {
  selectionLabel: string
  ratingBucket: string
  cell: KpiHeatmapCell
}

type Props = {
  cells: KpiHeatmapCell[]
  onCellClick: (sel: KpiHeatmapSelection) => void
}

export function KpiSignalsHeatmapLab({ cells, onCellClick }: Props) {
  const map = new Map(cells.map((c) => [`${c.selection_label}|${c.rating_bucket}`, c]))

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-800">Heatmap Pronostico × Rating</h2>
      <p className="mt-1 text-xs text-slate-500">Clicca una cella per filtrare il dettaglio e aprire il drawer.</p>
      <div className="relative mt-4">
        <div className="overflow-x-auto rounded-xl pb-2 [-ms-overflow-style:none] [scrollbar-width:thin]">
          <table className="min-w-[720px] w-full border-separate border-spacing-1">
            <thead>
              <tr>
                <th className="px-2 py-2 text-left text-xs font-semibold text-slate-600">Pronostico</th>
                {KPI_RATING_BUCKETS.map((col) => (
                  <th key={col} className="px-1 py-2 text-center text-xs font-semibold text-slate-600">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {KPI_HEATMAP_ROWS.map((row) => (
                <tr key={row}>
                  <td className="px-2 py-1 text-xs font-medium text-slate-800">{row}</td>
                  {KPI_RATING_BUCKETS.map((col) => {
                    const cell = map.get(`${row}|${col}`)
                    return (
                      <td key={col} className="p-0.5">
                        <KpiCellLab
                          cell={cell}
                          onClick={() => {
                            if (cell && cell.activations > 0) {
                              onCellClick({ selectionLabel: row, ratingBucket: col, cell })
                            }
                          }}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
