import type { KpiHeatmapCell, KpiSignalsBucket } from '../../lib/cecchinoKpiSignalsApi'
import { formatOdds } from '../cecchino-lab/signalsLabUtils'

export function formatKpiWinRate(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${Number(value).toFixed(1)}%`
}

export function formatKpiRoi(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${Number(value).toFixed(2)}%`
}

export function formatKpiProfit(value: number | null | undefined): string {
  if (value == null) return '—'
  const n = Number(value)
  return n >= 0 ? `+${n.toFixed(2)}` : n.toFixed(2)
}

export function profitTextClass(value: number | null | undefined): string {
  if (value == null) return 'text-slate-600'
  if (value > 0.05) return 'text-emerald-700'
  if (value > 0) return 'text-emerald-600'
  if (value > -0.05) return 'text-amber-700'
  return 'text-rose-700'
}

export function kpiHeatmapCellStyle(cell: KpiHeatmapCell | undefined): string {
  if (!cell || cell.activations === 0) {
    return 'bg-white border-slate-100 text-slate-400'
  }
  if (cell.settled < 3) {
    return 'bg-slate-50 border-slate-200 text-slate-500'
  }
  const profit = cell.profit_units
  if (profit != null) {
    if (profit > 0.05) return 'bg-emerald-50/90 border-emerald-200/80 text-emerald-900'
    if (profit > 0) return 'bg-emerald-50/60 border-emerald-100 text-emerald-800'
    if (profit > -0.05) return 'bg-amber-50/80 border-amber-200/70 text-amber-900'
    return 'bg-red-50/80 border-red-200/70 text-red-900'
  }
  const rate = cell.win_rate
  if (rate == null) return 'bg-slate-50 border-slate-200 text-slate-600'
  if (rate >= 60) return 'bg-emerald-50/80 border-emerald-200/70 text-emerald-900'
  if (rate >= 50) return 'bg-amber-50/80 border-amber-200/70 text-amber-900'
  return 'bg-red-50/80 border-red-200/70 text-red-900'
}

export function bucketAccentClass(
  data: KpiSignalsBucket | undefined,
): { card: string; badge: string; glow: string } {
  if (!data || data.settled < 3) {
    return {
      card: 'from-slate-50/80 to-white border-slate-200',
      badge: 'bg-slate-100 text-slate-600',
      glow: 'shadow-slate-200/40',
    }
  }
  const profit = data.profit_units ?? 0
  if (profit > 0) {
    return {
      card: 'from-emerald-50/90 to-white border-emerald-200/80',
      badge: 'bg-emerald-100 text-emerald-800',
      glow: 'shadow-emerald-200/50',
    }
  }
  if (profit < 0) {
    return {
      card: 'from-rose-50/90 to-white border-rose-200/80',
      badge: 'bg-rose-100 text-rose-800',
      glow: 'shadow-rose-200/50',
    }
  }
  return {
    card: 'from-amber-50/80 to-white border-amber-200/80',
    badge: 'bg-amber-100 text-amber-800',
    glow: 'shadow-amber-200/40',
  }
}

export function kpiStatusLabel(status: string): string {
  switch (status) {
    case 'won':
      return 'Vinto'
    case 'lost':
      return 'Perso'
    case 'pending':
      return 'Pending'
    case 'result_missing':
      return 'In attesa risultato'
    case 'not_evaluable':
      return 'Non valutabile'
    default:
      return status
  }
}

export function kpiStatusBadgeClass(status: string): string {
  switch (status) {
    case 'won':
      return 'bg-emerald-100 text-emerald-800 ring-emerald-200/80'
    case 'lost':
      return 'bg-rose-100 text-rose-800 ring-rose-200/80'
    case 'pending':
    case 'result_missing':
      return 'bg-sky-100 text-sky-800 ring-sky-200/80'
    case 'not_evaluable':
      return 'bg-slate-100 text-slate-600 ring-slate-200/80'
    default:
      return 'bg-slate-100 text-slate-600'
  }
}

export function formatKpiOdds(value: number | null | undefined): string {
  return formatOdds(value)
}

export type KpiTopRow = {
  selection_label?: string
  rating_bucket?: string
  settled?: number
  win_rate?: number | null
  profit_units?: number | null
  roi_pct?: number | null
  activations?: number
}

export function parseKpiTopRow(raw: Record<string, unknown>): KpiTopRow {
  return {
    selection_label: typeof raw.selection_label === 'string' ? raw.selection_label : undefined,
    rating_bucket: typeof raw.rating_bucket === 'string' ? raw.rating_bucket : undefined,
    settled: typeof raw.settled === 'number' ? raw.settled : undefined,
    win_rate: typeof raw.win_rate === 'number' ? raw.win_rate : null,
    profit_units: typeof raw.profit_units === 'number' ? raw.profit_units : null,
    roi_pct: typeof raw.roi_pct === 'number' ? raw.roi_pct : null,
    activations: typeof raw.activations === 'number' ? raw.activations : undefined,
  }
}
