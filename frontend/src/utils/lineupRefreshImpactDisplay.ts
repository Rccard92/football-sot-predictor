/** Display variazione SOT pre/post refresh formazioni SportAPI. */

export type ImpactDirection = 'UP' | 'DOWN' | 'FLAT' | string | null | undefined

export const IMPACT_DIRECTION_NOTE =
  'La freccia indica la variazione dei SOT previsti, non la probabilità di vincita.'

export function impactBadgeClass(direction: ImpactDirection): string {
  const d = (direction || '').toUpperCase()
  if (d === 'UP') return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  if (d === 'DOWN') return 'border-rose-200 bg-rose-50 text-rose-900'
  return 'border-slate-200 bg-slate-100 text-slate-700'
}

export function formatImpactDelta(
  direction: ImpactDirection,
  delta: number | null | undefined,
): string {
  const d = (direction || '').toUpperCase()
  if (d === 'FLAT' || delta == null) return '= stabile'
  const n = Number(delta)
  if (!Number.isFinite(n)) return '—'
  const sign = n > 0 ? '+' : ''
  const arrow = d === 'UP' ? '↑' : d === 'DOWN' ? '↓' : '='
  return `${arrow} ${sign}${n.toFixed(2)}`
}

export function formatImpactLine(
  direction: ImpactDirection,
  delta: number | null | undefined,
  mainReason?: string | null,
): string {
  const badge = formatImpactDelta(direction, delta)
  if (!mainReason) return badge
  return `${badge} — ${mainReason}`
}
