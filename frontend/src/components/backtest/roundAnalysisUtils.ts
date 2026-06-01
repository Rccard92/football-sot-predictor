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

export function modelDisplayBadgeClass(display: string | undefined): string {
  if (display === 'OK') return 'bg-emerald-100 text-emerald-800'
  if (display === 'WARNINGS') return 'bg-amber-100 text-amber-900'
  if (display === 'ERROR') return 'bg-rose-100 text-rose-800'
  return 'bg-slate-100 text-slate-600'
}

export function ndBadgeClass(): string {
  return 'bg-slate-100 text-slate-600'
}

export type PickCellDisplay = {
  label: string
  sublabel?: string
  isNd: boolean
  title?: string
}

function ndSublabel(block: RoundAnalysisModelBlock): { sublabel: string; title?: string } {
  const code = block.error_code || block.reason
  if (code && code !== 'INSUFFICIENT_HISTORY') {
    return {
      sublabel: code.length > 22 ? `${code.slice(0, 22)}…` : code,
      title: block.error_message || block.message || code,
    }
  }
  if (block.reason === 'INSUFFICIENT_HISTORY' || block.error_code === 'V11_INSUFFICIENT_PRIOR_MATCHES') {
    return { sublabel: 'Storico insuff.', title: block.error_message || block.message || undefined }
  }
  return {
    sublabel: block.error_code || block.message?.slice(0, 40) || 'N/D',
    title: block.error_message || block.message || undefined,
  }
}

export function pickCell(
  block: RoundAnalysisModelBlock | undefined,
  kind: 'aggressive' | 'cautious',
): PickCellDisplay {
  if (!block) {
    return { label: 'ND', sublabel: 'N/D', isNd: true }
  }
  if (block.status === 'error') {
    const { sublabel, title } = ndSublabel(block)
    return { label: 'ERR', sublabel, isNd: true, title }
  }
  if (block.status === 'no_prediction') {
    const { sublabel, title } = ndSublabel(block)
    return { label: 'ND', sublabel, isNd: true, title }
  }

  const line = kind === 'aggressive' ? block.aggressive_line : block.cautious_line
  const outcome = kind === 'aggressive' ? block.aggressive_outcome : block.cautious_outcome
  const advice = kind === 'aggressive' ? block.aggressive_advice : block.cautious_advice

  if (line == null && block.predicted_total_sot == null) {
    const { sublabel, title } = ndSublabel(block)
    return { label: 'ND', sublabel, isNd: true, title }
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
