import type { RoundAnalysisModelBlock } from '../../lib/api'

export function hitRateBadgeClass(hitRate: number | null | undefined): string {
  if (hitRate == null) return 'bg-slate-100 text-slate-600'
  if (hitRate >= 70) return 'bg-emerald-100 text-emerald-800'
  if (hitRate >= 55) return 'bg-amber-100 text-amber-900'
  return 'bg-rose-100 text-rose-800'
}

export function dataQualityBadgeClass(badge: string | null | undefined): string {
  if (badge === 'OK') return 'bg-emerald-100 text-emerald-800'
  if (badge === 'Avvisi') return 'bg-amber-100 text-amber-900'
  if (badge === 'Critico') return 'bg-rose-100 text-rose-800'
  return 'bg-slate-100 text-slate-600'
}

export function ndBadgeClass(): string {
  return 'bg-slate-100 text-slate-600'
}

export type PickCellDisplay = {
  label: string
  sublabel?: string
  isNd: boolean
}

export function pickCell(
  block: RoundAnalysisModelBlock | undefined,
  kind: 'aggressive' | 'cautious',
): PickCellDisplay {
  if (!block) {
    return { label: 'ND', sublabel: 'Storico insuff.', isNd: true }
  }
  if (block.status === 'no_prediction') {
    const sub =
      block.reason === 'INSUFFICIENT_HISTORY'
        ? 'Storico insuff.'
        : block.message?.slice(0, 40) || 'N/D'
    return { label: 'ND', sublabel: sub, isNd: true }
  }

  const line = kind === 'aggressive' ? block.aggressive_line : block.cautious_line
  const outcome = kind === 'aggressive' ? block.aggressive_outcome : block.cautious_outcome
  const advice = kind === 'aggressive' ? block.aggressive_advice : block.cautious_advice

  if (line == null && block.predicted_total_sot == null) {
    return { label: 'ND', sublabel: 'Storico insuff.', isNd: true }
  }
  if (line == null) {
    return { label: advice || 'ND', sublabel: undefined, isNd: !advice }
  }
  return { label: `${line} · ${outcome ?? '—'}`, sublabel: undefined, isNd: false }
}

export const MODEL_KEYS = {
  v11: 'baseline_v1_1_sot',
  v20: 'baseline_v2_0_lineup_impact',
  v21: 'baseline_v2_1_weighted_components',
} as const

export function seasonLabelFromYear(year: number): string {
  return `${year}/${year + 1}`
}

export function statusLabelIt(status: string | undefined): string {
  switch (status) {
    case 'completed':
      return 'Completata'
    case 'completed_with_warnings':
      return 'Completata con avvisi'
    case 'failed':
      return 'Fallita'
    default:
      return status ?? '—'
  }
}
