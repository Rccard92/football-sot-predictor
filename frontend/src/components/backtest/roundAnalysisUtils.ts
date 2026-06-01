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

export function pickCell(
  block: RoundAnalysisModelBlock | undefined,
  kind: 'aggressive' | 'cautious',
): { label: string; outcome?: string | null; advice?: string | null } {
  if (!block) return { label: '—' }
  const line = kind === 'aggressive' ? block.aggressive_line : block.cautious_line
  const outcome = kind === 'aggressive' ? block.aggressive_outcome : block.cautious_outcome
  const advice = kind === 'aggressive' ? block.aggressive_advice : block.cautious_advice
  if (line == null) return { label: advice || 'N/D', outcome, advice }
  return { label: `${line} · ${outcome ?? '—'}`, outcome, advice }
}

export const MODEL_KEYS = {
  v11: 'baseline_v1_1_sot',
  v20: 'baseline_v2_0_lineup_impact',
  v21: 'baseline_v2_1_weighted_components',
} as const
