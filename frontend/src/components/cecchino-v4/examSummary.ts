/**
 * Numeri chiave di un esame: da 6 a 8 voci, mai il JSON grezzo.
 * E1 → criteri e Brier per famiglia; E2 → verdetto per statistica; E4 → ROI, intervallo, giocate, criteri.
 * Forma sconosciuta → griglia dei valori semplici di primo livello.
 */

import type { V4ExamOutcome, V4ExamResult } from '../../lib/cecchinoV4Api'
import { V4_EXAM_OUTCOME_LABELS, familyLabel, statLabel } from './constants'
import { capitalize, fmtCount, fmtDecimal, fmtRoiWithCi, fmtSigned } from './format'

export type ExamSummaryRow = {
  label: string
  value: string
  /** Se presente, il valore si mostra come chip d'esito. */
  outcome?: V4ExamOutcome
}

const MAX_ROWS = 8
const HIDDEN_KEYS = new Set(['code', 'title', 'preregistration', 'computed_at', 'passed', 'exam', 'engine_version'])
const OUTCOMES = new Set<string>(['superato', 'non_superato', 'in_attesa'])

type Obj = Record<string, unknown>

function isObj(v: unknown): v is Obj {
  return v != null && typeof v === 'object' && !Array.isArray(v)
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

function yesNo(v: unknown): string {
  return v === true ? 'sì' : v === false ? 'no' : '–'
}

function humanKey(k: string): string {
  return capitalize(k.replaceAll('_', ' '))
}

function fmtNumber(v: number): string {
  if (Number.isInteger(v)) return fmtCount(v)
  return new Intl.NumberFormat('it-IT', { maximumFractionDigits: 4 }).format(v)
}

function fmtSimple(v: unknown): string | null {
  if (typeof v === 'boolean') return yesNo(v)
  if (isNum(v)) return fmtNumber(v)
  if (typeof v === 'string') return OUTCOMES.has(v) ? V4_EXAM_OUTCOME_LABELS[v as V4ExamOutcome] : v
  return null
}

function criteriaRows(criteria: unknown): ExamSummaryRow[] {
  if (!isObj(criteria)) return []
  return Object.entries(criteria)
    .filter(([, v]) => typeof v === 'boolean')
    .map(([k, v]) => ({ label: `Criterio ${k}`, value: yesNo(v) }))
}

/** Griglia generica: valori semplici di primo livello, al massimo 8. */
export function genericRows(result: V4ExamResult | undefined): ExamSummaryRow[] {
  if (!result) return []
  const out: ExamSummaryRow[] = []
  for (const [k, v] of Object.entries(result)) {
    if (HIDDEN_KEYS.has(k) || k.startsWith('runtime')) continue
    const s = fmtSimple(v)
    if (s == null) continue
    const row: ExamSummaryRow = { label: humanKey(k), value: s }
    if (typeof v === 'string' && OUTCOMES.has(v)) row.outcome = v as V4ExamOutcome
    out.push(row)
    if (out.length >= MAX_ROWS) break
  }
  return out
}

function e1Rows(result: V4ExamResult): ExamSummaryRow[] {
  const out: ExamSummaryRow[] = criteriaRows(result.criteria)
  const final = isObj(result.final) ? result.final : null
  const accuracy = final && isObj(final.accuracy) ? final.accuracy : null
  const families = accuracy && isObj(accuracy.families) ? accuracy.families : null
  if (families) {
    for (const [fam, f] of Object.entries(families)) {
      if (!isObj(f)) continue
      if (isNum(f.mean_brier_reference) && isNum(f.mean_brier)) {
        out.push({
          label: `Brier ${familyLabel(fam)} · V3 → V4`,
          value: `${fmtDecimal(f.mean_brier_reference, 4)} → ${fmtDecimal(f.mean_brier, 4)}`,
        })
      }
    }
  } else {
    // Forma compatta: { brier: { v4, v3 }, log_loss: { v4, v3 } }
    for (const [key, name] of [
      ['brier', 'Brier'],
      ['log_loss', 'Log loss'],
    ] as const) {
      const b = result[key]
      if (isObj(b) && isNum(b.v3) && isNum(b.v4)) {
        out.push({ label: `${name} · V3 → V4`, value: `${fmtDecimal(b.v3, 4)} → ${fmtDecimal(b.v4, 4)}` })
      }
    }
    for (const [k, v] of Object.entries(result)) {
      if (typeof v === 'boolean' && !HIDDEN_KEYS.has(k)) out.push({ label: humanKey(k), value: yesNo(v) })
    }
  }
  return out.slice(0, MAX_ROWS)
}

function e2Rows(result: V4ExamResult): ExamSummaryRow[] {
  const out: ExamSummaryRow[] = []
  const stats = isObj(result.stats) ? result.stats : null
  if (stats) {
    for (const [stat, s] of Object.entries(stats)) {
      if (!isObj(s) || typeof s.verdict !== 'string' || !OUTCOMES.has(s.verdict)) continue
      const outcome = s.verdict as V4ExamOutcome
      out.push({ label: capitalize(statLabel(stat)), value: V4_EXAM_OUTCOME_LABELS[outcome], outcome })
    }
  } else {
    for (const [k, v] of Object.entries(result)) {
      if (typeof v === 'string' && OUTCOMES.has(v)) {
        const outcome = v as V4ExamOutcome
        out.push({ label: humanKey(k), value: V4_EXAM_OUTCOME_LABELS[outcome], outcome })
      }
    }
  }
  return out.slice(0, MAX_ROWS)
}

function e4Rows(result: V4ExamResult): ExamSummaryRow[] {
  const out: ExamSummaryRow[] = []
  const roiBlock = isObj(result.roi) ? result.roi : null
  const roi = roiBlock ? roiBlock.roi : result.roi
  const ci = Array.isArray(result.roi_ci) ? result.roi_ci : null
  const lo = ci && isNum(ci[0]) ? ci[0] : null
  const hi = ci && isNum(ci[1]) ? ci[1] : null
  if (isNum(roi)) out.push({ label: 'ROI (intervallo 90%)', value: fmtRoiWithCi(roi, lo, hi) })
  const plays = roiBlock && isNum(roiBlock.plays) ? roiBlock.plays : isNum(result.plays) ? result.plays : null
  if (plays != null) out.push({ label: 'Giocate', value: fmtCount(plays) })
  const profit = roiBlock && isNum(roiBlock.profit_units) ? roiBlock.profit_units : null
  if (profit != null) out.push({ label: 'Profitto (unità)', value: fmtSigned(profit, 2) })
  out.push(...criteriaRows(result.criteria))
  return out.slice(0, MAX_ROWS)
}

export function examSummaryRows(code: string, result: V4ExamResult | undefined): ExamSummaryRow[] {
  if (!result || Object.keys(result).length === 0) return []
  const c = code.toUpperCase()
  let rows: ExamSummaryRow[] = []
  if (c.startsWith('E1')) rows = e1Rows(result)
  else if (c.startsWith('E2')) rows = e2Rows(result)
  else if (c.startsWith('E4')) rows = e4Rows(result)
  return rows.length > 0 ? rows : genericRows(result)
}
