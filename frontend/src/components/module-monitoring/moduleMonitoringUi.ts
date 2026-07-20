export type MonitoringAccent = 'purchasability' | 'balance' | 'goal' | 'signals'

export const ACCENT_CLASSES: Record<
  MonitoringAccent,
  {
    ring: string
    chip: string
    softBg: string
    text: string
    border: string
    gradient: string
    chartPrimary: string
    chartSecondary: string
  }
> = {
  purchasability: {
    ring: 'ring-cyan-500/30',
    chip: 'bg-cyan-50 text-cyan-800 border-cyan-200',
    softBg: 'bg-gradient-to-br from-cyan-50/80 to-indigo-50/50',
    text: 'text-cyan-700',
    border: 'border-cyan-200/70',
    gradient: 'from-cyan-600 to-indigo-500',
    chartPrimary: '#0891b2',
    chartSecondary: '#6366f1',
  },
  balance: {
    ring: 'ring-violet-500/30',
    chip: 'bg-violet-50 text-violet-800 border-violet-200',
    softBg: 'bg-gradient-to-br from-violet-50/80 to-blue-50/50',
    text: 'text-violet-700',
    border: 'border-violet-200/70',
    gradient: 'from-violet-600 to-blue-500',
    chartPrimary: '#7c3aed',
    chartSecondary: '#3b82f6',
  },
  goal: {
    ring: 'ring-amber-500/30',
    chip: 'bg-amber-50 text-amber-900 border-amber-200',
    softBg: 'bg-gradient-to-br from-amber-50/80 to-orange-50/50',
    text: 'text-amber-700',
    border: 'border-amber-200/70',
    gradient: 'from-amber-500 to-orange-500',
    chartPrimary: '#f59e0b',
    chartSecondary: '#f97316',
  },
  signals: {
    ring: 'ring-emerald-500/30',
    chip: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    softBg: 'bg-gradient-to-br from-emerald-50/80 to-teal-50/50',
    text: 'text-emerald-700',
    border: 'border-emerald-200/70',
    gradient: 'from-emerald-600 to-teal-500',
    chartPrimary: '#059669',
    chartSecondary: '#14b8a6',
  },
}

export const STATUS_CLASSES = {
  success: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  collecting: 'bg-cyan-50 text-cyan-800 border-cyan-200',
  warning: 'bg-amber-50 text-amber-900 border-amber-200',
  blocked: 'bg-rose-50 text-rose-800 border-rose-200',
  unavailable: 'bg-slate-100 text-slate-600 border-slate-200',
} as const

export type StatusTone = keyof typeof STATUS_CLASSES

export const CARD_BASE =
  'rounded-2xl border border-slate-200/70 bg-white shadow-sm'

export const HERO_BASE =
  'rounded-3xl border border-slate-200/60 bg-gradient-to-br from-slate-50 via-white to-cyan-50/40 shadow-sm'

export const MOTION_FAST = { duration: 0.2 }
export const MOTION_MED = { duration: 0.25 }

export const READINESS_LABELS: Record<string, string> = {
  data_quality_blocked: 'Qualità dati insufficiente',
  insufficient_temporal_span: 'Periodo insufficiente',
  insufficient_sample: 'Campione insufficiente',
  collecting_data: 'Raccolta dati',
  performance_not_confirmed: 'Prestazioni non confermate',
  eligible_for_manual_promotion: 'Pronta per revisione manuale',
  candidate_under_review: 'Candidato in revisione',
  official_monitored: 'Ufficiale monitorato',
  preview_research: 'Preview research',
  operational: 'Operativo',
  preview_monitored: 'Preview monitorata',
}

export function readinessLabelIt(status: string | null | undefined): string {
  if (!status) return 'Stato non disponibile'
  return READINESS_LABELS[status] || status
}

/** Label italiane per status overview/API — raw key solo via aria-label. */
export function monitoringStatusLabel(status: string | null | undefined): string {
  return readinessLabelIt(status)
}

export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return '—'
  return Number(n).toFixed(digits)
}

export function fmtPct(
  n: number | null | undefined,
  alreadyPercent = false,
): string {
  if (n == null || Number.isNaN(n)) return '—'
  const v = alreadyPercent ? n : n * 100
  return `${v.toFixed(1)}%`
}

export function coverageDisplay(
  coverage: number | null | undefined,
  denomKnown: boolean,
): { text: string; tone: StatusTone } {
  if (!denomKnown || coverage == null) {
    return { text: 'Raccolta dati non ancora disponibile', tone: 'unavailable' }
  }
  if (coverage === 0) {
    return { text: '0%', tone: 'collecting' }
  }
  return {
    text: fmtPct(coverage),
    tone: coverage >= 0.95 ? 'success' : coverage >= 0.5 ? 'warning' : 'collecting',
  }
}

const SCIENTIFIC_MATURITY_LABELS: Record<string, string> = {
  raccolta_dati: 'Raccolta dati',
  campione_insufficiente: 'Campione insufficiente',
  validazione_in_corso: 'Validazione in corso',
  validazione_empirica_da_avviare: 'Validazione empirica da avviare',
  evidenza_sufficiente: 'Evidenza sufficiente',
  pronta_per_revisione: 'Pronta per revisione',
  promossa: 'Promossa',
  monitoraggio: 'Monitoraggio',
  partial_collecting: 'Raccolta dati',
  partial: 'Campione insufficiente',
}

export function scientificMaturityLabel(
  maturity: string | null | undefined,
  moduleKey?: string,
): string {
  if (maturity) {
    return SCIENTIFIC_MATURITY_LABELS[maturity] || maturity.replace(/_/g, ' ')
  }
  if (moduleKey === 'goal-intensity-v5') return 'Raccolta dati'
  if (moduleKey === 'balance-v5') return 'Validazione empirica da avviare'
  if (moduleKey === 'purchasability') return 'Campione insufficiente'
  if (moduleKey === 'signals') return 'Monitoraggio'
  return 'Raccolta dati'
}

export function operationalStatusLabel(
  status: string | null | undefined,
  fallback?: string,
): string {
  if (status) return monitoringStatusLabel(status)
  return fallback || 'Stato non disponibile'
}

type CoverageItem = {
  module_key?: string
  coverage?: number | null
  coverage_descriptive_ratio?: string | null
  coverage_numerator?: number | null
  coverage_denominator?: number | null
  timestamp_verified_ratio?: string | null
  global_snapshots?: number | null
  snapshots_in_period?: number | null
  historical_rows?: number | null
  validation_rows_total?: number | null
}

export function dataCoverageLabel(item: CoverageItem): string {
  const key = item.module_key
  if (key === 'balance-v5' && item.coverage_descriptive_ratio) {
    return `Copertura dati: ${item.coverage_descriptive_ratio}`
  }
  if (key === 'balance-v5' && item.coverage_numerator != null && item.coverage_denominator != null) {
    return `Copertura dati: ${item.coverage_numerator}/${item.coverage_denominator}`
  }
  if (key === 'goal-intensity-v5') {
    const global = item.global_snapshots
    const period = item.snapshots_in_period
    if (global != null && period != null) {
      return `Copertura dati: ${period} snapshot nel periodo (${global} globali)`
    }
  }
  if (key === 'purchasability' && item.validation_rows_total != null) {
    return `Copertura dati: ${item.validation_rows_total} righe validation`
  }
  if (key === 'signals' && item.historical_rows != null) {
    return `Copertura dati: ${item.historical_rows} attivazioni`
  }
  if (item.coverage != null) {
    return `Copertura dati: ${fmtPct(item.coverage)}`
  }
  return 'Copertura dati: non ancora disponibile'
}
