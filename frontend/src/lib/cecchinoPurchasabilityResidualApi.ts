import { AdminHttpError, adminGetJson, adminPostJson } from './api'
import {
  PURCHASABILITY_JOB_POLL_MS,
  formatElapsedMs,
  formatPurchasabilityJobError,
  type PurchasabilityResearchJobStartResponse,
  type PurchasabilityResearchJobStatus,
  type PurchasabilityStatFilters,
} from './cecchinoPurchasabilityStatisticalApi'

export { PURCHASABILITY_JOB_POLL_MS, formatElapsedMs, formatPurchasabilityJobError }
export type { PurchasabilityResearchJobStartResponse, PurchasabilityResearchJobStatus }

export type PurchasabilityResidualFilters = PurchasabilityStatFilters & {
  research_mode?: 'phase2a_residual_reliability'
}

export type PurchasabilityResidualExportKind =
  | 'summary'
  | 'cohort'
  | 'fair-book-audit'
  | 'feature-audit'
  | 'folds'
  | 'markets'
  | 'binary-results'
  | 'residual-results'
  | 'paired'
  | 'economic'
  | 'decisions'
  | 'readiness'

export type PurchasabilityResidualReliabilityResponse = {
  status: string
  version: string
  dataset_version: string
  source_statistical_version?: string
  source_settled_rows?: number
  research_banner?: string
  cohort_identity?: Record<string, unknown>
  oof_evaluation_identity?: Record<string, unknown>
  temporal_span?: Record<string, unknown>
  fair_book_probability_audit?: Record<string, unknown>
  residual_feature_audit?: Array<Record<string, unknown>>
  temporal_folds?: Array<Record<string, unknown>>
  market_results?: Array<Record<string, unknown>>
  binary_results?: Record<string, unknown>
  residual_results?: Record<string, unknown>
  paired_comparisons?: Record<string, unknown>
  economic_diagnostics?: Record<string, unknown>
  feature_decisions?: Array<Record<string, unknown>>
  phase_2b_residual_readiness?: Record<string, unknown>
  limitations?: string[]
  elapsed_ms?: Record<string, number>
  filters?: PurchasabilityResidualFilters
  no_db_writes?: boolean
  no_purchasability_formula?: boolean
}

const JOBS_BASE = '/api/admin/cecchino/research/purchasability/statistical-research/jobs'
const EXPORT_BASE = '/api/admin/cecchino/research/purchasability/residual-reliability/export'

function qs(filters: PurchasabilityResidualFilters): string {
  const p = new URLSearchParams()
  if (filters.date_from) p.set('date_from', filters.date_from)
  if (filters.date_to) p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.market_family) p.set('market_family', filters.market_family)
  if (filters.selection) p.set('selection', filters.selection)
  if (filters.bootstrap_iterations != null) {
    p.set('bootstrap_iterations', String(filters.bootstrap_iterations))
  }
  if (filters.seed != null) p.set('seed', String(filters.seed))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export function residualResearchTimeoutMs(bootstrapIterations?: number | null): number {
  const iterations = bootstrapIterations ?? 200
  if (iterations > 500) return 1_200_000
  if (iterations > 200) return 600_000
  return 300_000
}

export async function startPurchasabilityResidualJob(
  filters: PurchasabilityResidualFilters = {},
): Promise<PurchasabilityResearchJobStartResponse> {
  return adminPostJson(
    JOBS_BASE,
    {
      date_from: filters.date_from ?? null,
      date_to: filters.date_to ?? null,
      competition_id: filters.competition_id ?? null,
      market_family: filters.market_family ?? null,
      selection: filters.selection ?? null,
      bootstrap_iterations: filters.bootstrap_iterations ?? 200,
      seed: filters.seed ?? 42,
      research_mode: 'phase2a_residual_reliability',
    },
    { timeoutMs: 30_000 },
  )
}

export async function getPurchasabilityResidualJob(
  jobId: string,
): Promise<PurchasabilityResearchJobStatus> {
  return adminGetJson(`${JOBS_BASE}/${encodeURIComponent(jobId)}`, { timeoutMs: 15_000 })
}

export async function getPurchasabilityResidualJobSummary(
  jobId: string,
): Promise<PurchasabilityResidualReliabilityResponse> {
  return adminGetJson(`${JOBS_BASE}/${encodeURIComponent(jobId)}/summary`, {
    timeoutMs: 300_000,
  })
}

export async function getPurchasabilityResidualJobResult(
  jobId: string,
): Promise<PurchasabilityResidualReliabilityResponse> {
  return adminGetJson(`${JOBS_BASE}/${encodeURIComponent(jobId)}/result`, {
    timeoutMs: 300_000,
  })
}

export async function getActivePurchasabilityResidualJob(): Promise<{
  status: string
  job: PurchasabilityResearchJobStatus | null
}> {
  const res = await adminGetJson<{
    status: string
    job: PurchasabilityResearchJobStatus | null
  }>(`${JOBS_BASE}/active`, { timeoutMs: 15_000 })
  const job = res.job
  if (
    job &&
    (job as { research_mode?: string }).research_mode &&
    (job as { research_mode?: string }).research_mode !== 'phase2a_residual_reliability'
  ) {
    return { status: res.status, job: null }
  }
  // Also accept jobs whose filters.research_mode matches
  const mode =
    (job as { research_mode?: string } | null)?.research_mode ||
    (job?.filters as { research_mode?: string } | undefined)?.research_mode
  if (job && mode && mode !== 'phase2a_residual_reliability') {
    return { status: res.status, job: null }
  }
  return res
}

export function buildPurchasabilityResidualExportUrl(
  kind: PurchasabilityResidualExportKind,
  filters: PurchasabilityResidualFilters = {},
): string {
  return `${EXPORT_BASE}/${kind}${qs(filters)}`
}

export function formatResidualJobError(err: unknown): string {
  if (err instanceof AdminHttpError) {
    const body = err.body as Record<string, unknown> | null
    const code = body && typeof body === 'object' ? String(body.error || '') : ''
    if (err.status === 409 && code === 'purchasability_research_job_already_running') {
      return 'È già in esecuzione un’altra ricerca Acquistabilità (statistica o residuale).'
    }
  }
  return formatPurchasabilityJobError(err)
}
