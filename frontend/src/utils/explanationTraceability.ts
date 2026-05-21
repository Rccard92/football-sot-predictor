/**
 * Conteggi e stato "Tracciabilità variabili" per Audit spiegazione previsione.
 * Solo derivazione da payload esistente (nessun ricalcolo modello).
 */

import type { AppliedVariableTraceRow, FrameworkConsistencySide } from '../types/sotExplanation'

export type TraceabilityStatusLabel =
  | 'OK'
  | 'OK con avvisi'
  | 'Parziale / fallback v1.1'
  | 'Da controllare'
  | 'Errore formula'

export type TraceabilityDerivedMetrics = {
  manifestDeclared: number
  tracedCount: number
  withValueAvailable: number
  formulaFinalCount: number
  contextRiskCount: number
  qualityDataCount: number
  missingDataRowCount: number
  notInTraceCount: number
  extraInTraceCount: number
  statusLabel: TraceabilityStatusLabel
  traceAlignedWithManifest: boolean
}

function valueIsPresent(v: unknown): boolean {
  if (v === null || v === undefined) return false
  if (typeof v === 'string' && v.trim() === '') return false
  if (typeof v === 'number' && Number.isNaN(v)) return false
  return true
}

/** Riga considerata senza dato utile: status missing o valore assente senza fallback. */
export function traceRowIsMissingData(r: AppliedVariableTraceRow): boolean {
  if ((r.status || '').toLowerCase() === 'missing') return true
  if (r.fallback_used) return false
  return !valueIsPresent(r.value)
}

/** Valore disponibile per la lettura (dato presente o fallback applicato). */
export function traceRowHasValueAvailable(r: AppliedVariableTraceRow): boolean {
  if (r.fallback_used) return true
  return valueIsPresent(r.value) && (r.status || '').toLowerCase() !== 'missing'
}

export function traceRowIsFormulaRole(r: AppliedVariableTraceRow): boolean {
  const role = r.application_role || ''
  return role === 'direct_formula_component' || role === 'component_input'
}

/** Conta nella formula numerica finale: solo termini sommati (direct_formula_component). */
export function traceRowCountsAsFormulaFinal(r: AppliedVariableTraceRow): boolean {
  return r.application_role === 'direct_formula_component' && !traceRowIsMissingData(r)
}

export function traceRowIsContextRisk(r: AppliedVariableTraceRow): boolean {
  return r.application_role === 'context_risk'
}

export function traceRowIsQualityControl(r: AppliedVariableTraceRow): boolean {
  return r.application_role === 'quality_control'
}

export type TraceFilter = 'all' | 'formula' | 'context' | 'quality' | 'missing'

export function traceRowMatchesFilter(r: AppliedVariableTraceRow, f: TraceFilter): boolean {
  if (f === 'all') return true
  if (f === 'formula') return traceRowCountsAsFormulaFinal(r)
  if (f === 'context') return traceRowIsContextRisk(r)
  if (f === 'quality') return traceRowIsQualityControl(r)
  if (f === 'missing') return traceRowIsMissingData(r)
  return true
}

function traceHasFallbackV11(trace: AppliedVariableTraceRow[]): boolean {
  return trace.some(
    (r) =>
      (r.trace_key === 'v20_context_lineup_impact_status' || r.key === 'v20_context_lineup_impact_status') &&
      String(r.value || '').includes('fallback_v11'),
  )
}

function deriveStatus(args: {
  formulaFinalCount: number
  traceAligned: boolean
  missingDataKeysLen: number
  manifestDeclared: number
  fallbackV11: boolean
}): TraceabilityStatusLabel {
  if (args.formulaFinalCount === 0) {
    if (args.manifestDeclared > 0 && args.fallbackV11) return 'Parziale / fallback v1.1'
    return 'Errore formula'
  }
  if (args.fallbackV11) return 'Parziale / fallback v1.1'
  if (!args.traceAligned) return 'Da controllare'
  if (args.missingDataKeysLen > 0) return 'OK con avvisi'
  return 'OK'
}

export function deriveTraceabilityForSide(
  trace: AppliedVariableTraceRow[],
  fc: FrameworkConsistencySide,
): TraceabilityDerivedMetrics {
  const manifestDeclared = fc.framework_applied_count
  const tracedCount = trace.length
  const withValueAvailable = trace.filter(traceRowHasValueAvailable).length
  const formulaFinalCount = trace.filter(traceRowCountsAsFormulaFinal).length
  const contextRiskCount = trace.filter(traceRowIsContextRisk).length
  const qualityDataCount = trace.filter(traceRowIsQualityControl).length
  const missingDataRowCount = trace.filter(traceRowIsMissingData).length
  const notInTraceCount = fc.missing_trace_keys?.length ?? 0
  const extraInTraceCount = fc.extra_trace_keys?.length ?? 0

  const traceAlignedWithManifest =
    manifestDeclared === fc.debug_trace_count &&
    tracedCount === fc.debug_trace_count &&
    notInTraceCount === 0 &&
    extraInTraceCount === 0

  const fallbackV11 = traceHasFallbackV11(trace)

  const statusLabel = deriveStatus({
    formulaFinalCount,
    traceAligned: traceAlignedWithManifest,
    missingDataKeysLen: fc.missing_data_keys?.length ?? 0,
    manifestDeclared,
    fallbackV11,
  })

  return {
    manifestDeclared,
    tracedCount,
    withValueAvailable,
    formulaFinalCount,
    contextRiskCount,
    qualityDataCount,
    missingDataRowCount,
    notInTraceCount,
    extraInTraceCount,
    statusLabel,
    traceAlignedWithManifest,
  }
}

export function roleLabel(role: string): string {
  if (role === 'direct_formula_component') return 'Formula finale'
  if (role === 'component_input') return 'Input componente'
  if (role === 'context_risk') return 'Contesto / rischio'
  if (role === 'quality_control') return 'Qualità dati'
  if (role === 'debug_only') return 'Solo debug'
  return role
}
