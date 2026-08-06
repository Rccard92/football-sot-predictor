/**
 * Risoluzione campi progresso / coverage Goal Intensity v5.
 * Allinea FE ai contratti backend prospective_progress e coverage_*.
 */

export type ProgressSource = Record<string, unknown> | null | undefined

export function resolveCompleted(progress: ProgressSource, fallbackNormalized?: ProgressSource): number {
  const p = progress || {}
  const n = fallbackNormalized || {}
  const v =
    p.completed ??
    n.completed_n ??
    n.completed_snapshots ??
    p.completed_n ??
    p.completed_snapshots ??
    0
  return typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0
}

export function resolvePending(progress: ProgressSource, fallbackNormalized?: ProgressSource): number {
  const p = progress || {}
  const n = fallbackNormalized || {}
  const v =
    p.pending ??
    n.pending_n ??
    n.pending_snapshots ??
    p.pending_n ??
    p.pending_snapshots ??
    0
  return typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0
}

export function resolveSnapshots(progress: ProgressSource, fallbackNormalized?: ProgressSource): number {
  const p = progress || {}
  const n = fallbackNormalized || {}
  const v = p.snapshots ?? n.total_snapshots ?? p.total_snapshots ?? 0
  return typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0
}

export function resolveMinimum(
  progress: ProgressSource,
  fallbackNormalized?: ProgressSource,
  policyMinimum = 200,
): number {
  const p = progress || {}
  const n = fallbackNormalized || {}
  const v =
    p.minimum ??
    n.minimum_prospective_matches ??
    p.minimum_prospective_matches ??
    policyMinimum
  const num = typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || policyMinimum
  return num > 0 ? num : policyMinimum
}

export function progressDerived(completed: number, minimum: number) {
  const min = minimum > 0 ? minimum : 200
  const progressPct = (completed / min) * 100
  const remaining = Math.max(0, min - completed)
  const excess = Math.max(0, completed - min)
  return {
    progress_pct: progressPct,
    remaining,
    excess,
    minimum_reached: completed >= min,
  }
}

export function coverageCount(
  block: ProgressSource,
  key: 'snapshots' | 'completed' | 'pending',
): number | null {
  if (!block) return null
  const v = block[key]
  if (v == null) return null
  const num = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(num) ? num : null
}

export function evidenceLabelIt(level: string | null | undefined, preferred: string | null | undefined): string {
  if (!level || level === 'insufficient_sample') return 'confronto non disponibile'
  if (level === 'low' || preferred === 'none') return 'differenza non conclusiva'
  if (preferred === 'left') return 'errore inferiore (sinistra)'
  if (preferred === 'right') return 'errore superiore (sinistra) / inferiore (destra)'
  return 'differenza non conclusiva'
}

export const BENCHMARK_MODEL_ORDER = [
  'GI_A_STRICT_CORE',
  'GI_B_RECENCY',
  'MT1_LONG_TERM',
  'GI_A_without_volatility',
  'GI_V4_EXPECTED_GOALS',
] as const

export const PHASE_2C_ACTIVE_CANDIDATES = [
  'GI_A_STRICT_CORE',
  'GI_B_RECENCY',
  'GI_E_PRIMARY_RECALIBRATED',
  'GI_F_REGULARIZED_PILLARS',
] as const

export const PHASE_2C_ARCHIVED_CANDIDATES = [
  'MT1_LONG_TERM',
  'GI_A_without_volatility',
] as const

export const PHASE_2C_HOLDOUT_MODELS = [
  'GI_V4_EXPECTED_GOALS',
  'GI_A_STRICT_CORE',
  'GI_B_RECENCY',
  'GI_E_PRIMARY_RECALIBRATED',
  'GI_F_REGULARIZED_PILLARS',
] as const

export const BENCHMARK_MODEL_LABELS: Record<string, string> = {
  GI_A_STRICT_CORE: 'Primary V5',
  GI_B_RECENCY: 'Challenger V5',
  MT1_LONG_TERM: 'Benchmark interno V5',
  GI_A_without_volatility: 'Senza volatilità V5',
  GI_V4_EXPECTED_GOALS: 'V4',
  GI_E_PRIMARY_RECALIBRATED: 'Primary ricalibrato',
  GI_F_REGULARIZED_PILLARS: 'Pilastri regolarizzati',
}

export function phase2cFreezeDisabled(
  data: { freeze_allowed?: boolean; status?: string } | null | undefined,
): boolean {
  if (!data) return true
  if (data.freeze_allowed === false) return true
  if (data.status === 'blocked') return true
  return false
}
