import { useMemo } from 'react'
import {
  HEATMAP_COLUMNS,
  HEATMAP_SIGNAL_ROWS,
  type SignalsBucket,
  type SignalsSummaryResponse,
} from '../../lib/cecchinoSignalsApi'
import { mergeTakenOddsBuckets } from './signalsLabUtils'
import { SignalCellLab } from './SignalCellLab'

export type HeatmapCellSelection = {
  signalGroup: string
  signalLabel: string
  sourceColumn: string
  bucket: SignalsBucket
}

type Props = {
  summary: SignalsSummaryResponse
  modelLabel: string
  weightsSubtitle: string
  onCellClick: (cell: HeatmapCellSelection) => void
}

function findCell(summary: SignalsSummaryResponse, signalGroup: string, sourceColumn: string) {
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

export function SignalsHeatmapLab({ summary, modelLabel, weightsSubtitle, onCellClick }: Props) {
  const columns = useMemo(() => [...HEATMAP_COLUMNS, 'TOTALE' as const], [])

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-800">
        Heatmap Segnale × Colonna — {modelLabel}
      </h2>
      {weightsSubtitle && <p className="mt-1 text-xs text-slate-500">{weightsSubtitle}</p>}
      <div className="relative mt-4">
        <div className="overflow-x-auto rounded-xl pb-2 [-ms-overflow-style:none] [scrollbar-width:thin]">
          <table className="min-w-[720px] w-full border-separate border-spacing-1">
            <thead>
              <tr>
                <th className="px-2 py-2 text-left text-xs font-semibold text-slate-600">Segnale</th>
                {columns.map((col) => (
                  <th key={col} className="px-1 py-2 text-center text-xs font-semibold text-slate-600">
                    {col === 'TOTALE' ? 'Totale' : col.replace('EXCEL_', 'Excel ')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {HEATMAP_SIGNAL_ROWS.map((row) => {
                const total = sumRow(summary, row.group)
                return (
                  <tr key={row.group}>
                    <td className="px-2 py-1 text-xs font-medium text-slate-800">{row.label}</td>
                    {columns.map((col) => {
                      if (col === 'TOTALE') {
                        return (
                          <td key={col} className="p-0.5">
                            <SignalCellLab
                              bucket={total}
                              onClick={() =>
                                onCellClick({
                                  signalGroup: row.group,
                                  signalLabel: row.label,
                                  sourceColumn: 'TOTALE',
                                  bucket: total,
                                })
                              }
                            />
                          </td>
                        )
                      }
                      const bucket = findCell(summary, row.group, col)
                      return (
                        <td key={col} className="p-0.5">
                          <SignalCellLab
                            bucket={bucket}
                            onClick={() =>
                              bucket &&
                              onCellClick({
                                signalGroup: row.group,
                                signalLabel: row.label,
                                sourceColumn: col,
                                bucket,
                              })
                            }
                          />
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
      <p className="mt-3 text-xs text-slate-500">
        UNDER 2.5 e OVER 2.5 sono valutati sul risultato Full Time. Clicca una cella per i dettagli.
      </p>
    </section>
  )
}
