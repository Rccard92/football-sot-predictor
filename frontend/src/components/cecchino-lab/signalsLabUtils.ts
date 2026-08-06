import type { SignalActivationRow, SignalsBucket, SignalsSummaryResponse } from '../../lib/cecchinoSignalsApi'
import {
  CURRENT_SIGNAL_FORMULA_VERSION,
  LEGACY_SIGNAL_FORMULA_VERSION,
} from '../../lib/cecchinoSignalsApi'

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

export function formatSignalFormulaVersion(value: string | null | undefined): string {
  if (!value || value === LEGACY_SIGNAL_FORMULA_VERSION || value === 'legacy' || value === 'v1') {
    return 'legacy'
  }
  if (
    value === CURRENT_SIGNAL_FORMULA_VERSION ||
    value === 'current' ||
    value === 'v3'
  ) {
    return 'corrente V3'
  }
  if (value === 'cecchino_signals_matrix_v2_draw_dfg' || value === 'v2') {
    return 'precedente V2'
  }
  return value
}

export function formatRawSignalValue(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return '—'
    const upper = trimmed.toUpperCase()
    if (upper === 'SI' || upper === 'NO') return upper
    return trimmed
  }
  // Non convertire booleani: il backend restituisce "SI"/"NO"
  return '—'
}

export function formatConsensusScalar(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'boolean') return value ? 'Sì' : 'No'
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '—'
  if (typeof value === 'string') return value.trim() ? value : '—'
  if (Array.isArray(value)) {
    const parts = value
      .map((item) => formatConsensusScalar(item))
      .filter((item) => item && item !== '—')
    return parts.length ? parts.join(', ') : '—'
  }
  try {
    return JSON.stringify(value)
  } catch {
    return '—'
  }
}

export function formatConsensusYesColumns(
  columns: SignalActivationRow['consensus_yes_columns'],
): string {
  if (columns == null) return '—'
  const list = Array.isArray(columns)
    ? columns
    : typeof columns === 'string'
      ? columns
          .split(',')
          .map((c) => c.trim())
          .filter(Boolean)
      : []
  if (!list.length) return '—'
  return list
    .map((col) => String(col).replace(/^EXCEL_/, 'Excel '))
    .join(', ')
}

export function formatConsensusRatio(row: Pick<
  SignalActivationRow,
  'consensus_yes_count' | 'consensus_available_count'
>): string {
  const yes = row.consensus_yes_count
  const available = row.consensus_available_count
  if (yes == null && available == null) return '—'
  return `${yes ?? 0}/${available ?? 0}`
}

export function acquisitionStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'acquired_consensus':
      return 'Acquisito'
    case 'rejected_insufficient_consensus':
      return 'Conferma insufficiente'
    case 'acquired_single_formula_exempt':
      return 'Esente 1/2'
    case 'legacy_unclassified':
      return 'Legacy'
    case 'no_raw_signal':
      return 'Nessun SI grezzo'
    default:
      return status?.trim() ? status : '—'
  }
}

export function acquisitionStatusBadgeClass(status: string | null | undefined): string {
  switch (status) {
    case 'acquired_consensus':
      return 'bg-emerald-100 text-emerald-800'
    case 'rejected_insufficient_consensus':
      return 'bg-amber-100 text-amber-900'
    case 'acquired_single_formula_exempt':
      return 'bg-sky-100 text-sky-800'
    case 'legacy_unclassified':
      return 'bg-slate-200 text-slate-700'
    default:
      return 'bg-slate-100 text-slate-600'
  }
}

export function acquiredBadgeLabel(isAcquired: boolean | null | undefined): string {
  if (isAcquired === true) return 'Acquisito'
  if (isAcquired === false) return 'Non acquisito'
  return '—'
}

export function acquiredBadgeClass(isAcquired: boolean | null | undefined): string {
  if (isAcquired === true) return 'bg-emerald-100 text-emerald-800'
  if (isAcquired === false) return 'bg-rose-100 text-rose-800'
  return 'bg-slate-100 text-slate-600'
}

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

import { isoDaysAgoLocal, todayLocalIso } from '../../utils/dateLocal'

export function isoDaysAgo(days: number): string {
  return isoDaysAgoLocal(days)
}

export function todayIso(): string {
  return todayLocalIso()
}

export const LAB_SELECTED_MODEL_KEY = 'cecchino_signals_lab_selected_model'
