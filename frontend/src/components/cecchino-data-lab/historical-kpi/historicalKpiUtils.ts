import { formatOdd } from '../../../lib/cecchinoLabApi'

export const RATING_BUCKETS = ['50-59', '60-69', '70-79', '80-89', '90-99', '100'] as const

export const MARKET_LABELS: Record<string, string> = {
  HOME: '1',
  DRAW: 'X',
  DRAW_PT: 'X PT',
  AWAY: '2',
  ONE_X: '1X',
  X_TWO: 'X2',
  ONE_TWO: '12',
  OVER_1_5: 'Over 1.5',
  OVER_2_5: 'Over 2.5',
  UNDER_2_5: 'Under 2.5',
  UNDER_3_5: 'Under 3.5',
  UNDER_PT_1_5: 'Under PT 1.5',
  OVER_PT_0_5: 'Over PT 0.5',
  OVER_PT_1_5: 'Over PT 1.5',
}

export function marketLabel(key: string): string {
  return MARKET_LABELS[key] ?? key
}

export function formatWinRate(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v.toFixed(1)}%`
}

export function formatRoi(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

export function formatProfit(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(2)} u`
}

export function formatOdds(v: number | null | undefined): string {
  return formatOdd(v)
}

export function roiColorClass(roi: number | null | undefined): string {
  if (roi == null || Number.isNaN(roi)) return 'text-[var(--lab-muted)]'
  if (roi > 0) return 'text-[var(--lab-ok)]'
  if (roi < 0) return 'text-[var(--lab-err)]'
  return 'text-[var(--lab-muted)]'
}

export function roiBgColor(roi: number | null | undefined): string {
  if (roi == null || Number.isNaN(roi)) return 'rgba(138,160,181,0.12)'
  if (roi > 0) return 'rgba(61,214,140,0.22)'
  if (roi < 0) return 'rgba(240,113,120,0.22)'
  return 'rgba(138,160,181,0.12)'
}

export function sampleClassOpacity(sampleClass: string): number {
  switch (sampleClass) {
    case 'very_small':
      return 0.35
    case 'small':
      return 0.55
    case 'medium':
      return 0.75
    case 'large':
      return 1
    default:
      return 0.5
  }
}

export function sampleClassBorder(sampleClass: string): string {
  switch (sampleClass) {
    case 'very_small':
      return '1px dashed rgba(138,160,181,0.45)'
    case 'small':
      return '1px solid rgba(138,160,181,0.35)'
    case 'medium':
      return '1px solid rgba(46,230,255,0.25)'
    case 'large':
      return '1px solid rgba(46,230,255,0.45)'
    default:
      return '1px solid var(--lab-border)'
  }
}

export function quoteTypeMatchesFilter(
  cellQuoteType: string,
  filterQuoteType: 'real' | 'derived' | 'all' | undefined,
): boolean {
  const qt = filterQuoteType ?? 'real'
  if (qt === 'all') return true
  return cellQuoteType === qt
}

export function scopeLabel(scope: string, isPartial?: boolean): string {
  if (scope === 'balanced_pilot') return 'Pilota bilanciato'
  if (isPartial || scope === 'pilot') return 'Test tecnico / pilota'
  return 'Completa'
}
