import { AdminHttpError, adminGetJson, adminPostJson } from './api'

export const PURCHASABILITY_VALIDATION_POLL_MS = 2000

export type PurchasabilityValidationFilters = {
  date_from?: string
  date_to?: string
  candidate_version?: string
  competition_id?: number
  market_key?: string
  score_band?: string
  evaluation_status?: string
  source_cohort?: string
  promotion_eligible_only?: boolean
  bootstrap_iterations?: number
}

export type PurchasabilityValidationJobStatus = {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | string
  current_stage?: string | null
  progress_message?: string | null
  created_at?: string
  started_at?: string | null
  completed_at?: string | null
  elapsed_seconds?: number | null
  filters?: PurchasabilityValidationFilters
  validation_version?: string
  policy_version?: string
  result_available?: boolean
  error_code?: string | null
  error_message?: string | null
  poll_after_ms?: number
}

export type PurchasabilityValidationSummary = {
  status: string
  version?: string
  policy_version?: string
  candidate_version?: string
  metrics?: Record<string, unknown>
  by_score_band?: Array<Record<string, unknown>>
  by_market_family?: Array<Record<string, unknown>>
  phase1_comparison?: Record<string, unknown>
  residual?: Record<string, unknown>
  temporal_folds?: Array<Record<string, unknown>>
  temporal_stability?: Record<string, unknown>
  temporal_span?: Record<string, unknown>
  promotion_is_automatic?: boolean
}

export type PurchasabilityValidationReadiness = {
  status: string
  policy_version?: string
  candidate_version?: string
  promotion_is_automatic?: boolean
  eligible_for_manual_promotion?: boolean
  data_gates?: Record<string, Record<string, unknown>>
  performance_gates?: Record<string, unknown>
  blocking_reasons?: string[]
  warnings?: string[]
  recommended_next_step?: string
  prima_data_teorica_promozione?: string | null
  summary_metrics?: Record<string, unknown>
}

export type PurchasabilityValidationHealth = {
  status: string
  eligible_today_fixtures?: number
  fixtures_with_kpi_panel?: number
  fixtures_with_persisted_preview?: number
  fixtures_with_verified_pre_match_preview?: number
  snapshot_persistence_coverage?: number | null
  result_pending_count?: number
  result_settled_count?: number
  duplicate_validation_rows?: number
  timestamp_mismatch_count?: number
}

const BASE = '/api/cecchino/kpi-signals/purchasability-validation'

function qs(filters: PurchasabilityValidationFilters): string {
  const p = new URLSearchParams()
  if (filters.date_from) p.set('date_from', filters.date_from)
  if (filters.date_to) p.set('date_to', filters.date_to)
  if (filters.candidate_version) p.set('candidate_version', filters.candidate_version)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.market_key) p.set('market_key', filters.market_key)
  if (filters.score_band) p.set('score_band', filters.score_band)
  if (filters.evaluation_status) p.set('evaluation_status', filters.evaluation_status)
  if (filters.source_cohort) p.set('source_cohort', filters.source_cohort)
  if (filters.promotion_eligible_only != null) {
    p.set('promotion_eligible_only', String(filters.promotion_eligible_only))
  }
  if (filters.bootstrap_iterations != null) {
    p.set('bootstrap_iterations', String(filters.bootstrap_iterations))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export function formatElapsedMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export function formatValidationJobError(err: unknown): string {
  if (err instanceof AdminHttpError) {
    const body = err.body as { message?: string; code?: string; detail?: string } | null
    return body?.message || body?.detail || body?.code || err.message
  }
  if (err instanceof Error) return err.message
  return String(err)
}

export async function getPurchasabilityValidationHealth(
  filters: PurchasabilityValidationFilters,
): Promise<PurchasabilityValidationHealth> {
  return adminGetJson(`${BASE}/health${qs(filters)}`)
}

export async function getPurchasabilityValidationSummary(
  filters: PurchasabilityValidationFilters,
): Promise<PurchasabilityValidationSummary> {
  return adminGetJson(`${BASE}/summary${qs(filters)}`)
}

export async function getPurchasabilityValidationReadiness(
  filters: PurchasabilityValidationFilters,
): Promise<PurchasabilityValidationReadiness> {
  return adminGetJson(`${BASE}/readiness${qs(filters)}`)
}

export async function getPurchasabilityValidationRows(
  filters: PurchasabilityValidationFilters & { limit?: number; offset?: number },
): Promise<{ total: number; items: Array<Record<string, unknown>> }> {
  const p = new URLSearchParams(qs(filters).replace(/^\?/, ''))
  if (filters.limit != null) p.set('limit', String(filters.limit))
  if (filters.offset != null) p.set('offset', String(filters.offset))
  const s = p.toString()
  return adminGetJson(`${BASE}/rows${s ? `?${s}` : ''}`)
}

export function buildPurchasabilityValidationExportUrl(
  filters: PurchasabilityValidationFilters,
): string {
  return `${BASE}/export.csv${qs(filters)}`
}

export async function startPurchasabilityValidationJob(
  filters: PurchasabilityValidationFilters,
): Promise<{ job_id: string; status: string; poll_after_ms?: number }> {
  return adminPostJson(`${BASE}/jobs`, {
    date_from: filters.date_from,
    date_to: filters.date_to,
    candidate_version: filters.candidate_version || undefined,
    competition_id: filters.competition_id ?? undefined,
    market_key: filters.market_key || undefined,
    bootstrap_iterations: filters.bootstrap_iterations ?? 200,
    promotion_eligible_only: filters.promotion_eligible_only ?? true,
  })
}

export async function getPurchasabilityValidationJob(
  jobId: string,
): Promise<PurchasabilityValidationJobStatus> {
  return adminGetJson(`${BASE}/jobs/${jobId}`)
}

export async function getPurchasabilityValidationJobResult(
  jobId: string,
): Promise<{ summary?: PurchasabilityValidationSummary; readiness?: PurchasabilityValidationReadiness }> {
  return adminGetJson(`${BASE}/jobs/${jobId}/result`)
}
