/** Helper presentazione KPI — nessuna logica di business. */

import {
  todayEdgeNegative,
  todayEdgeNeutral,
  todayEdgePositive,
} from './cecchinoTodayStyles'

export const KPI_PRIMARY_LABELS = new Set(['1', 'X', '2', '1X', 'X2', '12'])

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

export function isKpiAnalysisRow(label: string): boolean {
  return KPI_ANALYSIS_LABELS.has(label)
}

export function isKpiPrimaryRow(label: string): boolean {
  return KPI_PRIMARY_LABELS.has(label)
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
