import type { SignalActivationRow, SignalsBucket } from '../../../lib/cecchinoSignalsApi'

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
  if (signal_group === 'UNDER_UNDER_PT') return 'UNDER 2.5'
  if (signal_group === 'OVER_OVER_PT') return 'OVER 2.5'
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
