import { AdminHttpError, adminGetJson } from './api'

export type MonitoringModuleKeyApi =
  | 'purchasability'
  | 'balance-v5'
  | 'goal-intensity-v5'
  | 'signals'

export type ModuleOverviewItem = {
  module_key: MonitoringModuleKeyApi | string
  status?: string | null
  scientific_maturity?: string | null
  version?: string | null
  coverage?: number | null
  fixtures?: number | null
  settled?: number | null
  last_snapshot_at?: string | null
  next_review_at?: string | null
  warnings?: string[]
  eligible_fixtures?: number | null
  covered_fixtures?: number | null
  settled_covered_fixtures?: number | null
  coverage_numerator?: number | null
  coverage_denominator?: number | null
  coverage_descriptive_ratio?: string | null
  timestamp_verified_ratio?: string | null
  activations?: number | null
  prospective_rows?: number | null
  historical_rows?: number | null
  prospective_fixtures?: number | null
  historical_fixtures?: number | null
  historical_settled_rows?: number | null
  evaluated_rows?: number | null
  pending_rows?: number | null
  result_missing_rows?: number | null
  data_quality_excluded_rows?: number | null
  invalid_book_odds_count?: number | null
  readiness_status?: string | null
  validation_rows_total?: number | null
  validation_rows_by_source_cohort?: Record<string, number> | null
  reconciliation?: Record<string, number> | null
  settled_historical?: number | null
  prospective_persisted?: number | null
  prospective_snapshots?: number | null
  reconstructed_fixtures?: number | null
  timestamp_verified_fixtures?: number | null
  coverage_descriptive?: number | null
  timestamp_verified_coverage?: number | null
  prospective_coverage?: number | null
  global_snapshots?: number | null
  snapshots_in_period?: number | null
  pending_snapshots?: number | null
  completed_snapshots?: number | null
  minimum_sample?: number | null
  snapshot_collection_progress?: number | null
  completed_results_progress?: number | null
  monitoring_status?: string | null
  first_effective_date?: string | null
  last_effective_date?: string | null
  fixtures_with_current_signals?: number | null
  current_activations?: number | null
  current_activations_evaluated?: number | null
  historical_activations_total?: number | null
  verified_pre_match_count?: number | null
  post_kickoff_excluded_count?: number | null
  unusable_count?: number | null
  historical_activations?: number | null
  settled_activations?: number | null
  persistence_blocking_reason?: string | null
}

export type ModuleMonitoringOverview = {
  generated_at: string
  modules: ModuleOverviewItem[]
}

export type ModuleMonitoringFilters = {
  date_from: string
  date_to: string
  competition_id?: number
  market_key?: string
  include_rows?: boolean
  include_debug?: boolean
  source_cohort?: string
}

const BASE = '/api/cecchino/module-monitoring'

function qs(filters: ModuleMonitoringFilters): string {
  const p = new URLSearchParams()
  p.set('date_from', filters.date_from)
  p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.market_key) p.set('market_key', filters.market_key)
  if (filters.include_rows != null) p.set('include_rows', String(filters.include_rows))
  if (filters.include_debug != null) p.set('include_debug', String(filters.include_debug))
  if (filters.source_cohort && filters.source_cohort !== 'all') {
    p.set('source_cohort', filters.source_cohort)
  } else if (filters.source_cohort === 'all') {
    p.set('source_cohort', 'all')
  }
  return `?${p.toString()}`
}

function apiBase(): string {
  return (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
}

async function downloadBlob(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`${apiBase()}${path}`)
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      message = body?.detail || body?.message || message
    } catch {
      /* ignore */
    }
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^"]+)"?/i.exec(cd)
  const filename = match?.[1] || fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export async function getModuleMonitoringOverview(
  filters: Pick<ModuleMonitoringFilters, 'date_from' | 'date_to' | 'competition_id'>,
): Promise<ModuleMonitoringOverview> {
  const p = new URLSearchParams()
  p.set('date_from', filters.date_from)
  p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  return adminGetJson(`${BASE}/overview?${p.toString()}`)
}

export async function downloadModuleAnalysisPack(
  moduleKey: MonitoringModuleKeyApi,
  filters: ModuleMonitoringFilters,
): Promise<void> {
  await downloadBlob(
    `${BASE}/${moduleKey}/analysis-pack.zip${qs(filters)}`,
    `SOT_MONITOR_${moduleKey}_${filters.date_from}_${filters.date_to}.zip`,
  )
}

export async function downloadModuleSummaryJson(
  moduleKey: MonitoringModuleKeyApi,
  filters: ModuleMonitoringFilters,
): Promise<void> {
  await downloadBlob(
    `${BASE}/${moduleKey}/summary.json${qs({ ...filters, include_rows: false })}`,
    `SOT_MONITOR_${moduleKey}_summary.json`,
  )
}

export async function downloadModuleRowsCsv(
  moduleKey: MonitoringModuleKeyApi,
  filters: ModuleMonitoringFilters,
): Promise<void> {
  await downloadBlob(
    `${BASE}/${moduleKey}/rows.csv${qs({ ...filters, include_rows: true })}`,
    `SOT_MONITOR_${moduleKey}_${filters.date_from}_${filters.date_to}_rows.csv`,
  )
}

export type ModuleExportStatus = {
  module_key: string
  files_expected: string[]
  files_available: string[]
  rows: number | null
  source_cohorts?: Record<string, number> | null
  completeness: 'complete' | 'partial' | 'empty' | 'blocked' | string
  export_completeness_status?: string
  blocking_reasons?: string[]
  estimated_size_bytes?: number | null
  warnings?: string[]
}

export async function getModuleExportStatus(
  moduleKey: MonitoringModuleKeyApi,
  filters: ModuleMonitoringFilters,
): Promise<ModuleExportStatus> {
  return adminGetJson(
    `${BASE}/${moduleKey}/export-status${qs({ ...filters, include_rows: filters.include_rows ?? true })}`,
  )
}

export function formatExportCompletenessLabel(status: ModuleExportStatus | null | undefined): string {
  if (!status) return 'Stato export non disponibile'
  const rows = status.rows
  const c = status.completeness || status.export_completeness_status || 'partial'
  if (c === 'complete') {
    return rows != null ? `Completo · ${rows.toLocaleString('it-IT')} righe` : 'Completo'
  }
  if (c === 'empty') {
    return 'Raccolta dati · 0 righe prospettiche'
  }
  if (c === 'blocked') {
    const reason = status.blocking_reasons?.[0]
    return reason ? `Bloccato · ${reason}` : 'Bloccato'
  }
  const reason = status.blocking_reasons?.[0] || status.warnings?.[0]
  if (rows != null && rows > 0) {
    return reason
      ? `Parziale · ${rows.toLocaleString('it-IT')} righe · ${reason}`
      : `Parziale · ${rows.toLocaleString('it-IT')} righe`
  }
  return reason ? `Parziale · ${reason}` : 'Parziale · pacchetto incompleto'
}

export function formatEstimatedSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export const HISTORICAL_BACKFILL_CONFIRM =
  'IMPORT_CECCHINO_HISTORICAL_MONITORING'

export type HistoricalBackfillPlan = Record<string, unknown> & {
  version?: string
  modules?: Record<string, Record<string, unknown>>
}

export async function planHistoricalBackfill(body: {
  module_keys: string[]
  date_from: string
  date_to: string
  competition_id?: number | null
  include_unverified_diagnostic?: boolean
}): Promise<HistoricalBackfillPlan> {
  const { adminPostJson } = await import('./api')
  return adminPostJson(
    '/api/admin/cecchino/module-monitoring/historical-backfill/plan',
    body,
  )
}

export async function runHistoricalBackfill(body: {
  module_keys: string[]
  date_from: string
  date_to: string
  competition_id?: number | null
  include_unverified_diagnostic?: boolean
  evaluate_after?: boolean
  confirm: string
}): Promise<HistoricalBackfillPlan> {
  const { adminPostJson } = await import('./api')
  return adminPostJson(
    '/api/admin/cecchino/module-monitoring/historical-backfill/run',
    body,
  )
}

export type PackAuditItem = {
  module_key: string
  status?: string
  completeness?: string
  technical_status?: string
  scientific_status?: string
  error_code?: string
  error_type?: string
  export_audit?: {
    status?: string
    technical_status?: string
    scientific_status?: string
    source_row_count?: number
    exported_row_count?: number
    truncated?: boolean
    missing_files?: string[]
    missing_columns?: Record<string, string[]> | string[]
    row_count_match?: boolean
    actual_files?: string[]
    required_files?: string[]
    error_code?: string
    error_type?: string
  }
  files_available?: string[] | number
  files_expected?: string[] | null
  rows?: number | null
  source_cohorts?: Record<string, number>
  blocking_reasons?: string[]
}

/** Timeout dedicato audit forensic (4 moduli) — non modifica il default 90s delle altre GET. */
export const ANALYSIS_PACKS_AUDIT_TIMEOUT_MS = 240_000

export async function getAnalysisPacksAudit(
  filters: Pick<
    ModuleMonitoringFilters,
    'date_from' | 'date_to' | 'competition_id' | 'source_cohort'
  >,
  opts?: { timeoutMs?: number; signal?: AbortSignal },
): Promise<{ modules: PackAuditItem[]; export_version?: string }> {
  const p = new URLSearchParams()
  p.set('date_from', filters.date_from)
  p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.source_cohort) p.set('source_cohort', filters.source_cohort)
  return adminGetJson(`${BASE}/analysis-packs-audit?${p.toString()}`, {
    timeoutMs: opts?.timeoutMs ?? ANALYSIS_PACKS_AUDIT_TIMEOUT_MS,
    signal: opts?.signal,
  })
}

export type CohortFilterValue =
  | 'all'
  | 'prospective_persisted'
  | 'historical_persisted_verified'
  | 'historical_reconstructed_verified'
  | 'historical_diagnostic'

export const COHORT_FILTER_OPTIONS: { value: CohortFilterValue; label: string }[] = [
  { value: 'all', label: 'Tutte le coorti' },
  { value: 'prospective_persisted', label: 'Prospettica' },
  { value: 'historical_persisted_verified', label: 'Storica persistita verificata' },
  { value: 'historical_reconstructed_verified', label: 'Storica ricostruita verificata' },
  { value: 'historical_diagnostic', label: 'Storica diagnostica' },
]

export const BALANCE_EMPIRICAL_SYNC_CONFIRM =
  'SYNC_BALANCE_V5_EMPIRICAL_DATASET'

export type BalanceEmpiricalHealth = {
  status?: string
  dataset_version?: string
  target_contract_version?: string
  balance_version?: string
  readiness?: string
  cardinality?: Record<string, unknown>
  timestamp_verified?: number
  timestamp_unverified?: number
  pre_match_snapshots?: number
  book_verified?: number
  analysis_eligible?: number
  promotion_eligible?: number
  notes?: string[]
}

export type BalanceEmpiricalCardinality = {
  status?: string
  dataset_version?: string
  fixtures?: number
  rows?: number
  settled?: number
  pending?: number
  verified?: number
  diagnostic?: number
  prospective?: number
  analysis_eligible?: number
  promotion_eligible?: number
  by_source_cohort?: Record<string, number>
  by_evaluation_status?: Record<string, number>
}

export type BalanceEmpiricalSyncResult = Record<string, unknown> & {
  dry_run?: boolean
  dataset_version?: string
  source_fixtures?: number
  rows_new?: number
  rows_updatable?: number
  rows_skipped?: number
  inserted?: number
  updated?: number
  settled?: number
  pending?: number
  failed?: number
}

function balanceEmpiricalQuery(
  filters: Pick<ModuleMonitoringFilters, 'date_from' | 'date_to' | 'competition_id'> & {
    source_cohort?: string
  },
): string {
  const p = new URLSearchParams()
  p.set('date_from', filters.date_from)
  p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.source_cohort && filters.source_cohort !== 'all') {
    p.set('source_cohort', filters.source_cohort)
  }
  return p.toString()
}

export async function getBalanceEmpiricalHealth(
  filters: Pick<ModuleMonitoringFilters, 'date_from' | 'date_to' | 'competition_id'> & {
    source_cohort?: string
  },
): Promise<BalanceEmpiricalHealth> {
  return adminGetJson(
    `${BASE}/balance-v5/empirical/health?${balanceEmpiricalQuery(filters)}`,
  )
}

export async function getBalanceEmpiricalSummary(
  filters: Pick<ModuleMonitoringFilters, 'date_from' | 'date_to' | 'competition_id'> & {
    source_cohort?: string
  },
): Promise<Record<string, unknown>> {
  return adminGetJson(
    `${BASE}/balance-v5/empirical/summary?${balanceEmpiricalQuery(filters)}`,
  )
}

export async function getBalanceEmpiricalCardinality(
  filters: Pick<ModuleMonitoringFilters, 'date_from' | 'date_to' | 'competition_id'> & {
    source_cohort?: string
  },
): Promise<BalanceEmpiricalCardinality> {
  return adminGetJson(
    `${BASE}/balance-v5/empirical/cardinality?${balanceEmpiricalQuery(filters)}`,
  )
}

export async function getBalanceEmpiricalTargetContract(): Promise<Record<string, unknown>> {
  return adminGetJson(`${BASE}/balance-v5/empirical/target-contract`)
}

export async function getBalanceEmpiricalRows(
  filters: Pick<ModuleMonitoringFilters, 'date_from' | 'date_to' | 'competition_id'> & {
    source_cohort?: string
    evaluation_status?: string
    limit?: number
    offset?: number
  },
): Promise<{ items?: unknown[]; total?: number }> {
  const p = new URLSearchParams(balanceEmpiricalQuery(filters))
  if (filters.evaluation_status) p.set('evaluation_status', filters.evaluation_status)
  if (filters.limit != null) p.set('limit', String(filters.limit))
  if (filters.offset != null) p.set('offset', String(filters.offset))
  return adminGetJson(`${BASE}/balance-v5/empirical/rows?${p.toString()}`)
}

export async function planBalanceEmpiricalSync(body: {
  date_from: string
  date_to: string
  competition_id?: number | null
  source_cohort?: string
}): Promise<BalanceEmpiricalSyncResult> {
  const { adminPostJson } = await import('./api')
  return adminPostJson(
    '/api/admin/cecchino/module-monitoring/balance-v5/empirical-sync/plan',
    body,
  )
}

export async function runBalanceEmpiricalSync(body: {
  date_from: string
  date_to: string
  competition_id?: number | null
  source_cohort?: string
  confirm: string
}): Promise<BalanceEmpiricalSyncResult> {
  const { adminPostJson } = await import('./api')
  return adminPostJson(
    '/api/admin/cecchino/module-monitoring/balance-v5/empirical-sync/run',
    body,
  )
}

export type BalanceAnalysisPayload = Record<string, unknown> & {
  status?: string
  reading?: string
  banner?: string
  evidence?: Record<string, unknown>
  evidence_scope?: string
  sample?: Record<string, unknown>
  by_class?: Array<Record<string, unknown>>
}

export type BalanceAnalysisPillar =
  | 'overview'
  | 'f36'
  | 'dominance'
  | 'draw-credibility'
  | 'gap'
  | 'stability'
  | 'data-health'
  | 'dependency'

export async function getBalanceEmpiricalAnalysis(
  pillar: BalanceAnalysisPillar,
  filters: {
    date_from: string
    date_to: string
    competition_id?: number
    source_cohort?: string
    country_name?: string
    f36_class?: string
    dominance_class?: string
    dominance_selection?: string
    draw_credibility_class?: string
    gap_class?: string
  },
  signal?: AbortSignal,
): Promise<BalanceAnalysisPayload> {
  const p = new URLSearchParams()
  p.set('date_from', filters.date_from)
  p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.source_cohort) p.set('source_cohort', filters.source_cohort)
  if (filters.country_name) p.set('country_name', filters.country_name)
  if (filters.f36_class) p.set('f36_class', filters.f36_class)
  if (filters.dominance_class) p.set('dominance_class', filters.dominance_class)
  if (filters.dominance_selection) p.set('dominance_selection', filters.dominance_selection)
  if (filters.draw_credibility_class) {
    p.set('draw_credibility_class', filters.draw_credibility_class)
  }
  if (filters.gap_class) p.set('gap_class', filters.gap_class)
  return adminGetJson(`${BASE}/balance-v5/empirical/analysis/${pillar}?${p}`, {
    signal,
  })
}

export async function startBalanceEmpiricalAnalysisJob(body: {
  date_from: string
  date_to: string
  competition_id?: number | null
  source_cohort?: string
  bootstrap_iterations?: number
}): Promise<{ job_id: string; status: string; poll_after_ms?: number }> {
  const { adminPostJson } = await import('./api')
  return adminPostJson('/api/cecchino/module-monitoring/balance-v5/empirical/analysis/jobs', body)
}

export async function getBalanceEmpiricalAnalysisJob(
  jobId: string,
): Promise<Record<string, unknown>> {
  return adminGetJson(`${BASE}/balance-v5/empirical/analysis/jobs/${jobId}`)
}
