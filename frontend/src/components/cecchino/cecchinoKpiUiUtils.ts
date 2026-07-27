/** Helper presentazione KPI — nessuna logica di business. */

import {
  todayEdgeNegative,
  todayEdgeNeutral,
  todayEdgePositive,
} from './cecchinoTodayStyles'

export const KPI_PRIMARY_LABELS = new Set(['1', 'X', 'X PT', '2', '1X', 'X2', '12'])

export const KPI_OVER_LABELS = new Set([
  'OVER 1.5',
  'OVER 2.5',
  'OVER PT 0.5',
  'OVER PT 1.5',
  'Over 1.5',
  'Over 2.5',
  'Over PT 0.5',
  'Over PT 1.5',
  'Under 2.5',
  'Under 3.5',
  'Under PT1.5',
  'Under PT 1.5',
])

export const KPI_ANALYSIS_LABELS = new Set(['ANALISI DEL MATCH', 'DELTA DI FORZA'])

export function fmtKpiCell(
  v: string | number | null | undefined,
  asDecimal = false,
): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'string') return v
  if (asDecimal) return Number(v).toFixed(2)
  return String(v)
}

export function fmtProbPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${(Number(v) * 100).toFixed(2)}%`
}

export function fmtVantaggioProb(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  const pts = Number(v) * 100
  const sign = pts > 0 ? '+' : ''
  return `${sign}${pts.toFixed(2)} pp`
}

export function formatScorePercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

export function fmtScoreAcquisto(v: number | null | undefined): string {
  return formatScorePercent(v)
}

export function isKpiAnalysisRow(label: string): boolean {
  return KPI_ANALYSIS_LABELS.has(label)
}

export function isKpiPrimaryRow(label: string): boolean {
  return KPI_PRIMARY_LABELS.has(label)
}

export function isKpiOverRow(label: string): boolean {
  return KPI_OVER_LABELS.has(label)
}

export function edgeClassName(edge: number | null | undefined): string {
  if (edge == null || Number.isNaN(Number(edge))) return todayEdgeNeutral
  const n = Number(edge)
  if (n > 0) return todayEdgePositive
  if (n < 0) return todayEdgeNegative
  return todayEdgeNeutral
}

export function formatEdgePct(edge: number | null | undefined): string {
  if (edge == null || Number.isNaN(Number(edge))) return '—'
  return `${Number(edge).toFixed(2)}%`
}

export function vantaggioClassName(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return todayEdgeNeutral
  const n = Number(v)
  if (n > 0) return todayEdgePositive
  if (n < 0) return todayEdgeNegative
  return todayEdgeNeutral
}

export function ratingBadgeClass(label: string | null | undefined): string {
  switch (label) {
    case 'Elite':
    case 'Premium':
      return 'bg-emerald-600 text-white'
    case 'Forte':
      return 'bg-emerald-500/90 text-white'
    case 'Buona':
      return 'bg-sky-600 text-white'
    case 'Sufficiente':
      return 'bg-amber-500 text-white'
    case 'Debole':
      return 'bg-orange-500 text-white'
    case 'Scarto':
      return 'bg-slate-500 text-slate-100'
    default:
      return 'bg-slate-600 text-slate-200'
  }
}

export function purchasabilityBadgeClass(
  klass: string | null | undefined,
  calculationQuality?: 'full' | 'partial' | null,
): string {
  let base: string
  switch (klass) {
    case 'Molto Bassa':
      base = 'bg-slate-600 text-white'
      break
    case 'Bassa':
      base = 'bg-orange-600 text-white'
      break
    case 'Media':
      base = 'bg-amber-500 text-slate-950'
      break
    case 'Alta':
      base = 'bg-sky-500 text-white'
      break
    case 'Molto Alta':
      base = 'bg-emerald-500 text-white'
      break
    default:
      base = 'bg-slate-600 text-slate-200'
  }
  if (calculationQuality === 'partial') {
    return `${base} ring-1 ring-dashed ring-white/60`
  }
  return base
}

/** Stile più neutro per Acquistabilità v1.1 (baseline). */
export function purchasabilityV11BadgeClass(
  klass: string | null | undefined,
  calculationQuality?: 'full' | 'partial' | null,
): string {
  let base: string
  switch (klass) {
    case 'Molto Bassa':
      base = 'bg-slate-700/80 text-slate-200'
      break
    case 'Bassa':
      base = 'bg-slate-600/90 text-orange-100'
      break
    case 'Media':
      base = 'bg-slate-500/90 text-amber-100'
      break
    case 'Alta':
      base = 'bg-slate-500 text-sky-100'
      break
    case 'Molto Alta':
      base = 'bg-slate-500 text-emerald-100'
      break
    default:
      base = 'bg-slate-700 text-slate-300'
  }
  if (calculationQuality === 'partial') {
    return `${base} ring-1 ring-dashed ring-white/40`
  }
  return base
}

export function purchasabilityDeltaClass(delta: number | null | undefined): string {
  if (delta == null || Number.isNaN(Number(delta))) {
    return 'bg-slate-700/60 text-slate-400'
  }
  const d = Number(delta)
  if (d > 0) return 'bg-emerald-900/50 text-emerald-200'
  if (d < 0) return 'bg-rose-900/40 text-rose-200'
  return 'bg-slate-600/70 text-slate-300'
}

export function formatPurchasabilityDelta(delta: number | null | undefined): string {
  if (delta == null || Number.isNaN(Number(delta))) return '—'
  const d = Number(delta)
  if (d > 0) return `+${d}`
  return String(d)
}

export function historicalReliabilityBadgeClass(klass: string | null | undefined): string {
  switch (klass) {
    case 'Alta':
      return 'bg-emerald-600 text-white'
    case 'Buona':
      return 'bg-sky-600 text-white'
    case 'Incerta':
      return 'bg-slate-500 text-white'
    case 'Debole':
      return 'bg-orange-500/90 text-white'
    case 'Bassa':
      return 'bg-rose-700/80 text-white'
    default:
      return 'bg-slate-600 text-slate-200'
  }
}

export function fmtRoiPct(roi: number | null | undefined): string {
  if (roi == null || Number.isNaN(Number(roi))) return '—'
  const pct = Number(roi) * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}
