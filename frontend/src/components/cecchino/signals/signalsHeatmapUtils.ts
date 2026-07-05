import type { SignalActivationRow, SignalsBucket } from '../../../lib/cecchinoSignalsApi'
import { SIGNAL_DISPLAY_ORDER } from '../../../lib/cecchinoSignalsApi'

export function heatmapCellClass(bucket: SignalsBucket | undefined): string {
  if (!bucket || bucket.settled < 3) {
    return 'bg-slate-100 text-slate-600'
  }
  const rate = bucket.success_rate
  if (rate == null) return 'bg-slate-100 text-slate-600'
  if (rate >= 75) return 'bg-emerald-100 text-emerald-900'
  if (rate >= 60) return 'bg-emerald-50 text-emerald-800'
  if (rate >= 50) return 'bg-amber-50 text-amber-900'
  if (rate >= 40) return 'bg-orange-50 text-orange-900'
  return 'bg-red-50 text-red-900'
}

export function formatSuccessRate(rate: number | null | undefined): string {
  if (rate == null) return '—'
  return `${rate.toFixed(1)}%`
}

export function statusBadgeClass(status: string): string {
  switch (status) {
    case 'won':
      return 'bg-emerald-100 text-emerald-800'
    case 'lost':
      return 'bg-red-100 text-red-800'
    case 'pending':
    case 'result_missing':
      return 'bg-sky-100 text-sky-800'
    case 'not_evaluable':
      return 'bg-slate-100 text-slate-600'
    default:
      return 'bg-slate-100 text-slate-700'
  }
}

export function formatSignalLabel(signal_group: string, signal_label?: string): string {
  const fromOrder = SIGNAL_DISPLAY_ORDER.find((row) => row.group === signal_group)?.label
  if (fromOrder) return fromOrder
  return signal_label ?? signal_group
}

export function formatTargetLabel(row: Pick<SignalActivationRow, 'signal_group' | 'target_market_label'>): string {
  if (row.signal_group === 'UNDER_UNDER_PT') return 'Under 2.5 FT'
  if (row.signal_group === 'OVER_OVER_PT') return 'Over 2.5 FT'
  return row.target_market_label ?? '—'
}

export function statusLabel(status: string): string {
  switch (status) {
    case 'won':
      return 'WON'
    case 'lost':
      return 'LOST'
    case 'pending':
      return 'PENDING'
    case 'result_missing':
      return 'PENDING'
    case 'not_evaluable':
      return 'NOT EVALUABLE'
    default:
      return status.toUpperCase()
  }
}

export function formatOdds(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(2)
}

export function formatTakenProfit(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  const pct = value * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}

export function voidMarginClass(margin: number | null | undefined): string {
  if (margin == null || Number.isNaN(margin)) return 'text-slate-400'
  if (margin > 0) return 'text-emerald-700'
  if (margin < 0) return 'text-red-700'
  return 'text-slate-500'
}

export function formatVoidMargin(margin: number | null | undefined): string {
  if (margin == null || Number.isNaN(margin)) return '—'
  const sign = margin > 0 ? '+' : ''
  return `${sign}${margin.toFixed(2)}`
}

/** Ricalcola metriche quota prese da bucket parziali (es. riga Totale heatmap). */
export function mergeTakenOddsBuckets(cells: SignalsBucket[]): Partial<SignalsBucket> {
  let won = 0
  let lost = 0
  let pending = 0
  let notEval = 0
  let activations = 0
  let wonWithOdds = 0
  let sumWonOdds = 0

  for (const c of cells) {
    won += c.won
    lost += c.lost
    pending += c.pending
    notEval += c.not_evaluable
    activations += c.activations
    const wwo = c.won_with_odds ?? 0
    if (wwo > 0 && c.avg_won_book_odds != null) {
      wonWithOdds += wwo
      sumWonOdds += c.avg_won_book_odds * wwo
    }
  }

  const settled = won + lost
  const avgWon = wonWithOdds > 0 ? Math.round((sumWonOdds / wonWithOdds) * 100) / 100 : null
  const winRate = settled > 0 ? won / settled : null
  const quotaVoid = winRate && winRate > 0 ? Math.round((1 / winRate) * 100) / 100 : null
  const voidMargin =
    avgWon != null && quotaVoid != null ? Math.round((avgWon - quotaVoid) * 100) / 100 : null
  const takenYield =
    winRate != null && avgWon != null ? Math.round(winRate * avgWon * 1000) / 1000 : null
  const takenProfit = takenYield != null ? Math.round((takenYield - 1) * 1000) / 1000 : null

  return {
    activations,
    settled,
    won,
    lost,
    pending,
    not_evaluable: notEval,
    success_rate: settled > 0 ? Math.round((won / settled) * 1000) / 10 : null,
    won_with_odds: wonWithOdds,
    avg_won_book_odds: avgWon,
    quota_void: quotaVoid,
    void_margin: voidMargin,
    taken_yield_index: takenYield,
    taken_profit_indicator: takenProfit,
  }
}
