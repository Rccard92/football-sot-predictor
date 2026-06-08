/** Helper presentazione KPI — nessuna logica di business. */

import {
  todayEdgeNegative,
  todayEdgeNeutral,
  todayEdgePositive,
} from './cecchinoTodayStyles'

export const KPI_PRIMARY_LABELS = new Set(['1', 'X', '2', '1X', 'X2', '12'])

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

export function fmtScoreAcquisto(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(3)
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
