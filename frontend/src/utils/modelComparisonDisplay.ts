import { formatSignedNum } from '../components/upcoming/format'

export function deltaBadgeClass(totalDelta: number | null | undefined): string {
  if (totalDelta == null) return 'border-slate-200 bg-slate-50 text-slate-600'
  if (totalDelta >= 0.5) return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  if (totalDelta <= -0.5) return 'border-orange-200 bg-orange-50 text-orange-950'
  return 'border-slate-200 bg-slate-100 text-slate-700'
}

export function deltaBadgeLabel(totalDelta: number | null | undefined): string {
  if (totalDelta == null) return '—'
  if (totalDelta >= 0.5) return `↑ ${formatSignedNum(totalDelta)}`
  if (totalDelta <= -0.5) return `↓ ${formatSignedNum(totalDelta)}`
  return '≈ stabile'
}

export function pickShortFromLabel(pick: string | null | undefined): string {
  if (!pick) return '—'
  return pick.replace(/\s+SOT$/i, '').trim()
}
