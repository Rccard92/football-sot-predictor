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

/** Badge score V3 — colore = classe, non stato di validazione. */
export function purchasabilityV3BadgeClass(
  klass: string | null | undefined,
  calculationQuality?: 'full' | 'partial' | 'not_applicable' | string | null,
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

export type PurchasabilityV3CellKind =
  | 'score'
  | 'gate_failed'
  | 'missing_inputs'
  | 'unsupported'
  | 'snapshot_absent'
  | 'not_calculable'

export type PurchasabilityV3CellState = {
  kind: PurchasabilityV3CellKind
  primary: string
  subtitle: string | null
  showScoreBadge: boolean
  showCandidateChip: boolean
  derivedQuote: boolean
  analyzable: boolean
  score: number | null
  classLabel: string | null
  calculationQuality: string | null
}

function isDerivedQuoteItem(item: {
  input?: Record<string, number | string | boolean | null>
  reason_codes?: string[]
  penalties?: Record<string, { raw_inputs?: Record<string, number | string | boolean | null> }>
} | null | undefined): boolean {
  if (!item) return false
  const inp = item.input
  if (inp) {
    if (inp.performance_type === 'derived' || inp.not_real_book_quote === true) return true
    if (inp.diagnostic_only === true && inp.performance_type === 'derived') return true
  }
  const codes = item.reason_codes ?? []
  if (codes.some((c) => /derived|not_real_book/i.test(c))) return true
  const qq = item.penalties?.quote_quality?.raw_inputs
  if (qq?.performance_type === 'derived' || qq?.not_real_book_quote === true) return true
  return false
}

/**
 * Risolve lo stato visuale della cella Acquistabilità V3.
 * snapshotAvailable=false → snapshot assente; item undefined con snapshot → mercato senza item.
 */
export function resolvePurchasabilityV3CellState(
  item: {
    status?: string | null
    score?: number | null
    class?: string | null
    gate_status?: string | null
    calculation_quality?: string | null
    input?: Record<string, number | string | boolean | null>
    reason_codes?: string[]
    penalties?: Record<string, CecchinoPurchasabilityV3PenaltyLike>
  } | null | undefined,
  opts?: { snapshotAvailable?: boolean },
): PurchasabilityV3CellState {
  const snapshotAvailable = opts?.snapshotAvailable !== false
  const derived = isDerivedQuoteItem(item)

  if (!snapshotAvailable) {
    return {
      kind: 'snapshot_absent',
      primary: '—',
      subtitle: 'Non disponibile',
      showScoreBadge: false,
      showCandidateChip: false,
      derivedQuote: false,
      analyzable: false,
      score: null,
      classLabel: null,
      calculationQuality: null,
    }
  }

  if (!item) {
    return {
      kind: 'snapshot_absent',
      primary: '—',
      subtitle: 'Non disponibile',
      showScoreBadge: false,
      showCandidateChip: false,
      derivedQuote: false,
      analyzable: false,
      score: null,
      classLabel: null,
      calculationQuality: null,
    }
  }

  const gate = item.gate_status ?? null
  const status = item.status ?? 'unavailable'

  if (gate === 'unsupported_market') {
    return {
      kind: 'unsupported',
      primary: '—',
      subtitle: 'Non supportato',
      showScoreBadge: false,
      showCandidateChip: false,
      derivedQuote: false,
      analyzable: false,
      score: null,
      classLabel: null,
      calculationQuality: item.calculation_quality ?? null,
    }
  }

  if (gate === 'unavailable_inputs' || status === 'unavailable') {
    const hasScore = item.score != null
    if (!hasScore) {
      return {
        kind: gate === 'unavailable_inputs' ? 'missing_inputs' : 'not_calculable',
        primary: 'Non calcolabile',
        subtitle: 'Input mancanti',
        showScoreBadge: false,
        showCandidateChip: false,
        derivedQuote: derived,
        analyzable: true,
        score: null,
        classLabel: null,
        calculationQuality: item.calculation_quality ?? null,
      }
    }
  }

  const gateFailed =
    gate != null &&
    gate !== 'passed' &&
    gate !== 'unsupported_market' &&
    gate !== 'unavailable_inputs'

  if (gateFailed || (status === 'not_applicable' && item.score == null)) {
    return {
      kind: 'gate_failed',
      primary: 'Non attivato',
      subtitle: 'Nessun valore positivo',
      showScoreBadge: false,
      showCandidateChip: false,
      derivedQuote: derived,
      analyzable: true,
      score: null,
      classLabel: null,
      calculationQuality: item.calculation_quality ?? null,
    }
  }

  if (item.score != null && gate === 'passed') {
    return {
      kind: 'score',
      primary: String(item.score),
      subtitle: derived ? 'Quota derivata' : null,
      showScoreBadge: true,
      showCandidateChip: false,
      derivedQuote: derived,
      analyzable: true,
      score: item.score,
      classLabel: item.class ?? null,
      calculationQuality: item.calculation_quality ?? null,
    }
  }

  if (item.score != null) {
    return {
      kind: 'score',
      primary: String(item.score),
      subtitle: derived ? 'Quota derivata' : null,
      showScoreBadge: true,
      showCandidateChip: false,
      derivedQuote: derived,
      analyzable: true,
      score: item.score,
      classLabel: item.class ?? null,
      calculationQuality: item.calculation_quality ?? null,
    }
  }

  return {
    kind: 'not_calculable',
    primary: 'Non calcolabile',
    subtitle: 'Input mancanti',
    showScoreBadge: false,
    showCandidateChip: false,
    derivedQuote: derived,
    analyzable: true,
    score: null,
    classLabel: null,
    calculationQuality: item.calculation_quality ?? null,
  }
}

type CecchinoPurchasabilityV3PenaltyLike = {
  raw_inputs?: Record<string, number | string | boolean | null>
  penalty_points?: number | null
}

/** Formatta punti penalità con segno negativo esplicito (es. −35,00). */
export function formatPenaltyPointsNegative(
  points: number | null | undefined,
  digits = 2,
): string {
  if (points == null || Number.isNaN(Number(points))) return '—'
  const n = Math.abs(Number(points))
  const formatted = n.toLocaleString('it-IT', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  if (Number(points) === 0) return formatted
  return `−${formatted}`
}

export function formatV3Number(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('it-IT', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatV3PctFromFraction(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `${(Number(value) * 100).toLocaleString('it-IT', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`
}

export function formatV3PctAlready(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `${Number(value).toLocaleString('it-IT', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`
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

// ============================================================================
// Acquistabilità V3.1 Cell State Resolver
// ============================================================================

export type PurchasabilityV31CellKind =
  | 'score'
  | 'gate_failed'
  | 'non_calculable'
  | 'snapshot_absent'
  | 'loading'

export type PurchasabilityV31CellState = {
  kind: PurchasabilityV31CellKind
  primary: string
  subtitle: string | null
  showScoreBadge: boolean
  analyzable: boolean
  score: number | null
  classLabel: string | null
  reasonCode: string | null
}

const V31_NON_CALCULABLE_REASON_LABELS: Record<string, string> = {
  missing_quote: 'Quota mancante',
  derived_quote: 'Quota derivata',
  incomplete_set_book: 'Set Book incompleto',
  missing_cecchino_formula: 'Formula Cecchino mancante',
  insufficient_history: 'Storico insufficiente',
  complement_unavailable: 'Complemento non disponibile',
}

const V31_GATE_FAILED_REASON_LABELS: Record<string, string> = {
  no_positive_value: 'Nessun valore positivo',
  rating_below_50: 'Rating sotto 50',
}

/**
 * Risolve lo stato visuale della cella Acquistabilità V3.1.
 * - snapshotAvailable=false → snapshot assente
 * - loading=true → stato di caricamento
 * - item.status='score' → mostra score con badge
 * - item.status='gate_failed' → "Non attivato" con reason subtitle
 * - item.status='non_calculable' → "Non calcolabile" con reason subtitle
 */
export function resolvePurchasabilityV31CellState(
  item: {
    status?: 'score' | 'gate_failed' | 'non_calculable' | string | null
    score?: number | null
    class?: string | null
    reason?: string | null
    reason_code?: string | null
    gate_status?: string | null
    input?: Record<string, number | string | boolean | null>
  } | null | undefined,
  opts?: { snapshotAvailable?: boolean; loading?: boolean },
): PurchasabilityV31CellState {
  const snapshotAvailable = opts?.snapshotAvailable !== false
  const loading = opts?.loading === true

  if (loading) {
    return {
      kind: 'loading',
      primary: 'Calcolo in corso…',
      subtitle: null,
      showScoreBadge: false,
      analyzable: false,
      score: null,
      classLabel: null,
      reasonCode: null,
    }
  }

  if (!snapshotAvailable) {
    return {
      kind: 'snapshot_absent',
      primary: '—',
      subtitle: null,
      showScoreBadge: false,
      analyzable: false,
      score: null,
      classLabel: null,
      reasonCode: null,
    }
  }

  if (!item) {
    return {
      kind: 'snapshot_absent',
      primary: '—',
      subtitle: null,
      showScoreBadge: false,
      analyzable: false,
      score: null,
      classLabel: null,
      reasonCode: null,
    }
  }

  const status = item.status
  const reasonCode = item.reason_code ?? null
  const reason = item.reason ?? null

  if (status === 'gate_failed') {
    const subtitle =
      reasonCode && V31_GATE_FAILED_REASON_LABELS[reasonCode]
        ? V31_GATE_FAILED_REASON_LABELS[reasonCode]
        : reason ?? 'Nessun valore positivo'
    return {
      kind: 'gate_failed',
      primary: 'Non attivato',
      subtitle,
      showScoreBadge: false,
      analyzable: true,
      score: null,
      classLabel: null,
      reasonCode,
    }
  }

  if (status === 'non_calculable') {
    const subtitle =
      reasonCode && V31_NON_CALCULABLE_REASON_LABELS[reasonCode]
        ? V31_NON_CALCULABLE_REASON_LABELS[reasonCode]
        : reason ?? 'Input mancanti'
    return {
      kind: 'non_calculable',
      primary: 'Non calcolabile',
      subtitle,
      showScoreBadge: false,
      analyzable: true,
      score: null,
      classLabel: null,
      reasonCode,
    }
  }

  if (status === 'score' && item.score != null) {
    return {
      kind: 'score',
      primary: String(item.score),
      subtitle: null,
      showScoreBadge: true,
      analyzable: true,
      score: item.score,
      classLabel: item.class ?? null,
      reasonCode,
    }
  }

  if (item.score != null) {
    return {
      kind: 'score',
      primary: String(item.score),
      subtitle: null,
      showScoreBadge: true,
      analyzable: true,
      score: item.score,
      classLabel: item.class ?? null,
      reasonCode,
    }
  }

  return {
    kind: 'non_calculable',
    primary: 'Non calcolabile',
    subtitle: reason ?? 'Input mancanti',
    showScoreBadge: false,
    analyzable: true,
    score: null,
    classLabel: null,
    reasonCode,
  }
}

/** Badge class per Acquistabilità V3.1 (stessa palette di V3). */
export function purchasabilityV31BadgeClass(
  klass: string | null | undefined,
): string {
  switch (klass) {
    case 'Molto Bassa':
      return 'bg-slate-600 text-white'
    case 'Bassa':
      return 'bg-orange-600 text-white'
    case 'Media':
      return 'bg-amber-500 text-slate-950'
    case 'Alta':
      return 'bg-sky-500 text-white'
    case 'Molto Alta':
      return 'bg-emerald-500 text-white'
    default:
      return 'bg-slate-600 text-slate-200'
  }
}
