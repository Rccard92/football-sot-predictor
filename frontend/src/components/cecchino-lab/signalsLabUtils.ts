import type { SignalsBucket, SignalsSummaryResponse } from '../../lib/cecchinoSignalsApi'

export {
  formatOdds,
  formatSignalLabel,
  formatSuccessRate,
  formatTakenProfit,
  formatTargetLabel,
  formatVoidMargin,
  mergeTakenOddsBuckets,
  statusBadgeClass,
  statusLabel,
  voidMarginClass,
} from '../cecchino/signals/signalsHeatmapUtils'

export type ModelAccent = {
  ring: string
  bg: string
  bgSelected: string
  text: string
  glow: string
  letter: string
}

export const MODEL_ACCENT: Record<string, ModelAccent> = {
  A: {
    ring: 'ring-blue-400/60',
    bg: 'from-blue-50/80 to-white',
    bgSelected: 'from-blue-100/90 to-white',
    text: 'text-blue-800',
    glow: 'shadow-blue-200/50',
    letter: 'text-blue-600',
  },
  B: {
    ring: 'ring-cyan-400/60',
    bg: 'from-cyan-50/80 to-white',
    bgSelected: 'from-cyan-100/90 to-white',
    text: 'text-cyan-800',
    glow: 'shadow-cyan-200/50',
    letter: 'text-cyan-600',
  },
  C: {
    ring: 'ring-violet-400/60',
    bg: 'from-violet-50/80 to-white',
    bgSelected: 'from-violet-100/90 to-white',
    text: 'text-violet-800',
    glow: 'shadow-violet-200/50',
    letter: 'text-violet-600',
  },
  D: {
    ring: 'ring-emerald-400/60',
    bg: 'from-emerald-50/80 to-white',
    bgSelected: 'from-emerald-100/90 to-white',
    text: 'text-emerald-800',
    glow: 'shadow-emerald-200/50',
    letter: 'text-emerald-600',
  },
  E: {
    ring: 'ring-orange-400/60',
    bg: 'from-orange-50/80 to-white',
    bgSelected: 'from-orange-100/90 to-white',
    text: 'text-orange-800',
    glow: 'shadow-orange-200/50',
    letter: 'text-orange-600',
  },
  F: {
    ring: 'ring-teal-400/60',
    bg: 'from-slate-50/80 to-white',
    bgSelected: 'from-teal-50/90 to-white',
    text: 'text-teal-800',
    glow: 'shadow-teal-200/50',
    letter: 'text-teal-600',
  },
}

export function heatmapCellStyleByProfit(bucket: SignalsBucket | undefined): string {
  if (!bucket || bucket.activations === 0) {
    return 'bg-white border-slate-100 text-slate-400'
  }
  if (bucket.settled < 3) {
    return 'bg-slate-50 border-slate-200 text-slate-500'
  }
  const profit = bucket.taken_profit_indicator
  if (profit != null) {
    if (profit > 0.05) return 'bg-emerald-50/90 border-emerald-200/80 text-emerald-900'
    if (profit > 0) return 'bg-emerald-50/60 border-emerald-100 text-emerald-800'
    if (profit > -0.05) return 'bg-amber-50/80 border-amber-200/70 text-amber-900'
    return 'bg-red-50/80 border-red-200/70 text-red-900'
  }
  const rate = bucket.success_rate
  if (rate == null) return 'bg-slate-50 border-slate-200 text-slate-600'
  if (rate >= 60) return 'bg-emerald-50/80 border-emerald-200/70 text-emerald-900'
  if (rate >= 50) return 'bg-amber-50/80 border-amber-200/70 text-amber-900'
  return 'bg-red-50/80 border-red-200/70 text-red-900'
}

export type TopSortKey = 'taken_profit' | 'success_rate' | 'avg_won_book_odds' | 'settled'

export const TOP_SORT_OPTIONS: Array<{ value: TopSortKey; label: string }> = [
  { value: 'taken_profit', label: 'Rendimento' },
  { value: 'success_rate', label: 'Win Rate' },
  { value: 'avg_won_book_odds', label: 'Quota prese' },
  { value: 'settled', label: 'Segnali valutati' },
]

export function rankTopSignals(
  summary: SignalsSummaryResponse,
  sortBy: TopSortKey,
  minSettled = 5,
  limit = 10,
) {
  const filtered = summary.by_signal_and_column.filter((row) => row.settled >= minSettled)
  const sorter = (a: (typeof filtered)[0], b: (typeof filtered)[0]) => {
    switch (sortBy) {
      case 'success_rate':
        return (b.success_rate ?? 0) - (a.success_rate ?? 0)
      case 'avg_won_book_odds':
        return (b.avg_won_book_odds ?? 0) - (a.avg_won_book_odds ?? 0)
      case 'settled':
        return b.settled - a.settled
      case 'taken_profit':
      default:
        return (b.taken_profit_indicator ?? -999) - (a.taken_profit_indicator ?? -999)
    }
  }
  return [...filtered].sort(sorter).slice(0, limit)
}

export function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export const LAB_SELECTED_MODEL_KEY = 'cecchino_signals_lab_selected_model'
