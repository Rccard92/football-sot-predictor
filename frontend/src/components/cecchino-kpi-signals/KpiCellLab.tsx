import { memo } from 'react'
import type { KpiHeatmapCell } from '../../lib/cecchinoKpiSignalsApi'
import {
  formatKpiProfit,
  formatKpiRoi,
  formatKpiWinRate,
  kpiHeatmapCellStyle,
} from './kpiSignalsLabUtils'

type Props = {
  cell: KpiHeatmapCell | undefined
  onClick?: () => void
}

export const KpiCellLab = memo(function KpiCellLab({ cell, onClick }: Props) {
  const style = kpiHeatmapCellStyle(cell)
  const lowSample = cell != null && cell.settled > 0 && cell.settled < 3

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!cell || cell.activations === 0}
      className={`min-h-[92px] w-full rounded-xl border p-2 text-left text-xs transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md disabled:cursor-default disabled:hover:translate-y-0 disabled:hover:shadow-none ${style}`}
    >
      {!cell || cell.activations === 0 ? (
        <span className="text-slate-300">—</span>
      ) : (
        <div className="space-y-0.5 leading-tight">
          <div className="text-base font-bold tabular-nums">{cell.activations}</div>
          {cell.settled > 0 && (
            <div className="tabular-nums opacity-80">
              {cell.won}W / {cell.lost}L
            </div>
          )}
          {cell.settled >= 3 ? (
            <div className="font-semibold tabular-nums">{formatKpiWinRate(cell.win_rate)}</div>
          ) : lowSample ? (
            <span className="rounded bg-white/60 px-1 py-0.5 text-[9px] font-medium">campione basso</span>
          ) : null}
          {cell.pending > 0 && <div className="text-sky-700">+{cell.pending} pending</div>}
          {cell.profit_units != null && cell.settled >= 3 && (
            <div className="font-semibold tabular-nums">{formatKpiProfit(cell.profit_units)}</div>
          )}
          {cell.roi_pct != null && cell.settled >= 3 && (
            <div className="text-[10px] tabular-nums opacity-80">ROI {formatKpiRoi(cell.roi_pct)}</div>
          )}
        </div>
      )}
    </button>
  )
})
