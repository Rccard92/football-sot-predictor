import { memo } from 'react'
import type { SignalsBucket } from '../../lib/cecchinoSignalsApi'
import {
  formatOdds,
  formatSuccessRate,
  formatTakenProfit,
  formatVoidMargin,
  heatmapCellStyleByProfit,
} from './signalsLabUtils'

type Props = {
  bucket: SignalsBucket | undefined
  onClick?: () => void
}

export const SignalCellLab = memo(function SignalCellLab({ bucket, onClick }: Props) {
  const style = heatmapCellStyleByProfit(bucket)
  const lowSample = bucket != null && bucket.settled > 0 && bucket.settled < 3

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!bucket || bucket.activations === 0}
      className={`min-h-[88px] w-full rounded-xl border p-2 text-left text-xs transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md disabled:cursor-default disabled:hover:translate-y-0 disabled:hover:shadow-none ${style}`}
    >
      {!bucket || bucket.activations === 0 ? (
        <span className="text-slate-300">—</span>
      ) : (
        <div className="space-y-0.5 leading-tight">
          <div className="text-base font-bold tabular-nums">{bucket.activations}</div>
          {bucket.settled > 0 && (
            <div className="tabular-nums opacity-80">
              {bucket.won}W / {bucket.lost}L
            </div>
          )}
          {bucket.settled >= 3 ? (
            <div className="font-semibold tabular-nums">{formatSuccessRate(bucket.success_rate)}</div>
          ) : lowSample ? (
            <span className="rounded bg-white/60 px-1 py-0.5 text-[9px] font-medium">campione basso</span>
          ) : null}
          {bucket.pending > 0 && <div className="text-sky-700">+{bucket.pending} pending</div>}
          {(bucket.avg_won_book_odds != null || bucket.quota_void != null) && (
            <div className="mt-1 border-t border-current/10 pt-1 text-[10px] tabular-nums">
              QP {formatOdds(bucket.avg_won_book_odds)} · QV {formatOdds(bucket.quota_void)}
            </div>
          )}
          {bucket.taken_profit_indicator != null && bucket.settled >= 3 && (
            <div className="font-semibold tabular-nums">{formatTakenProfit(bucket.taken_profit_indicator)}</div>
          )}
          {bucket.void_margin != null && bucket.settled >= 3 && (
            <div className="text-[10px] opacity-75">MV {formatVoidMargin(bucket.void_margin)}</div>
          )}
        </div>
      )}
    </button>
  )
})
