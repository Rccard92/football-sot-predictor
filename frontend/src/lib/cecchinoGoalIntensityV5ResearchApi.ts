import { adminGetJson, adminPostJson } from './api'
import { sanitizeFilenameFragment } from './downloadJsonFile'

export type GoalIntensityV5AuditRequest = {
  date_from: string
  date_to: string
  competition_id?: number | null
}

export type GoalIntensityV5AvailabilityResponse = {
  status: string
  finished_fixtures_with_result: number
  earliest_kickoff: string | null
  latest_kickoff: string | null
  earliest_kickoff_date: string | null
  latest_kickoff_date: string | null
  competitions_count: number
  competition_ids: number[]
  countries_count: number
  countries: string[]
  cohort_basis: string
}

export type GoalIntensityFeatureInventoryRow = {
  feature_key: string
  pillar: string
  description: string
  source_table_or_payload: string
  source_version: string
  value_type: string
  rows_total: number
  rows_available: number
  rows_missing: number
  coverage_pct: number
  valid_numeric_rows: number
  invalid_rows: number
  min: number | null
  max: number | null
  mean: number | null
  median: number | null
  standard_deviation: number | null
  p10: number | null
  p25: number | null
  p75: number | null
  p90: number | null
  zero_rate: number | null
  outlier_rate: number | null
  pre_match_safe: boolean
  leakage_risk: string
  redundancy_family: string
  recommended_status: string
}

export type GoalIntensityXgStatus = 'available' | 'partial' | 'missing' | 'excluded_unsafe'

export type GoalIntensityFixtureAuditRow = {
  local_fixture_id: number
  provider_fixture_id: number | null
  competition_id: number | null
  country: string | null
  kickoff: string | null
  home_team: string | null
  away_team: string | null
  row_feature_safe: boolean
  static_identity_status: string
  snapshot_time_status: string
  xg_status: GoalIntensityXgStatus | string
  xg_source: string
  xg_available_fields: string[]
  xg_missing_fields: string[]
  xg_exclusion_reasons: string[]
  sample_size: number
  target_total_goals_ft: number | null
}

export type GoalIntensityV5AuditResponse = {
  status: string
  version: string
  filters: {
    date_from: string
    date_to: string
    competition_id: number | null
  }
  current_v4_inventory: Record<string, unknown>
  dataset_summary: Record<string, unknown>
  pillar_coverage: Record<string, Record<string, unknown>>
  feature_inventory: GoalIntensityFeatureInventoryRow[]
  fixture_audit_rows?: GoalIntensityFixtureAuditRow[]
  excluded_advanced_features: Array<Record<string, unknown>>
  anti_leakage: Record<string, unknown>
  exclusion_reasons?: Record<string, number>
  debug_samples?: Record<string, Array<Record<string, unknown>>>
  api_availability: Record<string, unknown>
  legacy_dependencies: Record<string, unknown>
  potential_conflicts: Array<Record<string, unknown>>
  interpretative_questions: string[]
  implementation_recommendation: Record<string, unknown>
  warnings: string[]
  performance: Record<string, unknown>
}

export function isGoalIntensityAuditUnusable(audit: GoalIntensityV5AuditResponse): boolean {
  const summary = audit.dataset_summary ?? {}
  if (summary.audit_quality === 'unusable') return true
  if (summary.audit_usable === false) return true
  const anti = audit.anti_leakage ?? {}
  const identityErrors = Number(anti.identity_check_errors ?? 0)
  if (identityErrors > 0) return true
  const inventory = audit.feature_inventory ?? []
  const localCount = Number(summary.local_fixtures_deduped ?? summary.rows_deduped ?? 0)
  const competitions = Number(summary.competitions ?? 0)
  if (localCount > 0 && competitions === 0) return true
  const sampleMean = Number(summary.sample_size_mean ?? 0)
  const safeRows = Number(summary.leakage_safe_rows ?? 0)
  if (safeRows > 0 && sampleMean === 0) return true
  if (inventory.length > 0 && inventory.every((f) => Number(f.coverage_pct) === 0)) return true
  const rate = Number(summary.feature_safe_rate_pct ?? -1)
  if (rate >= 0 && rate < 20) return true
  return false
}

export function isGoalIntensityAuditDegraded(audit: GoalIntensityV5AuditResponse): boolean {
  return (audit.dataset_summary ?? {}).audit_quality === 'degraded'
}

export function fetchGoalIntensityV5Availability(): Promise<GoalIntensityV5AvailabilityResponse> {
  return adminGetJson('/api/admin/cecchino/research/goal-intensity-v5/availability')
}

export function postGoalIntensityV5Audit(
  body: GoalIntensityV5AuditRequest,
): Promise<GoalIntensityV5AuditResponse> {
  return adminPostJson('/api/admin/cecchino/research/goal-intensity-v5/audit', body)
}

export type GoalIntensityV5DatasetRequest = GoalIntensityV5AuditRequest

export type GoalIntensityDatasetRow = Record<string, unknown> & {
  local_fixture_id: number
  sample_size?: number
  core_feature_status?: string
  xg_status?: string
  history_quality_tier?: string
}

export type GoalIntensityV5DatasetResponse = {
  status: string
  version: string
  filters: {
    date_from: string
    date_to: string
    competition_id: number | null
  }
  dataset_summary: Record<string, unknown>
  deduplication: Record<string, unknown>
  identity_diagnostics: Record<string, unknown>
  exclusion_bias_report: Record<string, unknown>
  history_quality: Record<string, unknown>
  xg_cohorts: Record<string, unknown>
  paired_xg_readiness: Record<string, unknown>
  feature_definitions: Array<Record<string, unknown>>
  /** Anteprima max 100 — non il dataset completo */
  dataset_preview_rows?: GoalIntensityDatasetRow[]
  /** @deprecated v1 only */
  dataset_rows?: GoalIntensityDatasetRow[]
  warnings: string[]
  performance: Record<string, unknown>
}

export function postGoalIntensityV5Dataset(
  body: GoalIntensityV5DatasetRequest,
): Promise<GoalIntensityV5DatasetResponse> {
  return adminPostJson('/api/admin/cecchino/research/goal-intensity-v5/dataset', body)
}

export type GoalIntensityDatasetExportKind =
  | 'all'
  | 'core_min5'
  | 'core_min10'
  | 'xg_paired'
  | 'summary'

const EXPORT_PATH: Record<GoalIntensityDatasetExportKind, string> = {
  all: '/api/admin/cecchino/research/goal-intensity-v5/dataset/export/all',
  core_min5: '/api/admin/cecchino/research/goal-intensity-v5/dataset/export/core-min5',
  core_min10: '/api/admin/cecchino/research/goal-intensity-v5/dataset/export/core-min10',
  xg_paired: '/api/admin/cecchino/research/goal-intensity-v5/dataset/export/xg-paired',
  summary: '/api/admin/cecchino/research/goal-intensity-v5/dataset/export/summary',
}

export async function postGoalIntensityV5DatasetExport(
  kind: GoalIntensityDatasetExportKind,
  body: GoalIntensityV5DatasetRequest,
  opts?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<{ blob: Blob; filename: string }> {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''
  const timeoutMs = opts?.timeoutMs ?? 300_000
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const onOuterAbort = () => controller.abort()
  opts?.signal?.addEventListener('abort', onOuterAbort)
  try {
    const res = await fetch(`${base}${EXPORT_PATH[kind]}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date_from: body.date_from,
        date_to: body.date_to,
        competition_id: body.competition_id ?? null,
      }),
      signal: controller.signal,
    })
    if (!res.ok) {
      let message = res.statusText
      const ct = res.headers.get('content-type') ?? ''
      if (ct.includes('application/json')) {
        try {
          const parsed = (await res.json()) as { detail?: string; message?: string }
          message = parsed.detail ?? parsed.message ?? message
        } catch {
          /* ignore */
        }
      }
      throw new Error(message || `HTTP ${res.status}`)
    }
    const disposition = res.headers.get('content-disposition') ?? ''
    const match = /filename="([^"]+)"/.exec(disposition)
    const fallback =
      kind === 'summary'
        ? buildGoalIntensityDatasetSummaryJsonFilename(body.date_from, body.date_to)
        : buildGoalIntensityDatasetCsvFilename(kind, body.date_from, body.date_to)
    return { blob: await res.blob(), filename: match?.[1] ?? fallback }
  } finally {
    clearTimeout(timer)
    opts?.signal?.removeEventListener('abort', onOuterAbort)
  }
}

export function classifyGoalIntensityFetchError(
  err: unknown,
  context: 'summary' | 'export',
): string {
  const msg = err instanceof Error ? err.message : String(err)
  const lower = msg.toLowerCase()
  if (err instanceof DOMException && err.name === 'AbortError') {
    return context === 'summary'
      ? 'Timeout costruzione summary dataset'
      : 'Timeout export dataset'
  }
  if (lower.includes('timeout') || lower.includes('abort')) {
    return context === 'summary'
      ? 'Timeout costruzione summary dataset'
      : 'Timeout export dataset'
  }
  if (lower.includes('failed to fetch') || lower.includes('network')) {
    return 'Errore di rete'
  }
  return `Errore backend: ${msg}`
}

export function buildGoalIntensityAuditJsonFilename(dateFrom: string, dateTo: string): string {
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  return `cecchino_goal_intensity_v5_audit_${from}_${to}.json`
}

export function buildGoalIntensityFeatureInventoryCsvFilename(
  dateFrom: string,
  dateTo: string,
): string {
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  return `cecchino_goal_intensity_v5_feature_inventory_${from}_${to}.csv`
}

export function buildGoalIntensityFixtureAuditCsvFilename(
  dateFrom: string,
  dateTo: string,
): string {
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  return `cecchino_goal_intensity_v5_fixture_audit_${from}_${to}.csv`
}

function escapeCsvCell(v: unknown): string {
  const s = v == null ? '' : String(v)
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

export function featureInventoryToCsv(rows: GoalIntensityFeatureInventoryRow[]): string {
  const headers = [
    'feature_key',
    'pillar',
    'description',
    'source_table_or_payload',
    'source_version',
    'value_type',
    'rows_total',
    'rows_available',
    'rows_missing',
    'coverage_pct',
    'valid_numeric_rows',
    'invalid_rows',
    'min',
    'max',
    'mean',
    'median',
    'standard_deviation',
    'p10',
    'p25',
    'p75',
    'p90',
    'zero_rate',
    'outlier_rate',
    'pre_match_safe',
    'leakage_risk',
    'redundancy_family',
    'recommended_status',
  ]
  const lines = [headers.join(',')]
  for (const row of rows) {
    lines.push(headers.map((h) => escapeCsvCell((row as Record<string, unknown>)[h])).join(','))
  }
  return lines.join('\n')
}

const FIXTURE_AUDIT_CSV_HEADERS = [
  'local_fixture_id',
  'provider_fixture_id',
  'competition_id',
  'country',
  'kickoff',
  'home_team',
  'away_team',
  'row_feature_safe',
  'static_identity_status',
  'snapshot_time_status',
  'xg_status',
  'xg_source',
  'xg_available_fields',
  'xg_missing_fields',
  'xg_exclusion_reasons',
  'sample_size',
  'target_total_goals_ft',
] as const

export function fixtureAuditToCsv(rows: GoalIntensityFixtureAuditRow[]): string {
  const lines = [FIXTURE_AUDIT_CSV_HEADERS.join(',')]
  for (const row of rows) {
    const cells = FIXTURE_AUDIT_CSV_HEADERS.map((h) => {
      const raw = (row as Record<string, unknown>)[h]
      if (Array.isArray(raw)) return escapeCsvCell(raw.join('|'))
      return escapeCsvCell(raw)
    })
    lines.push(cells.join(','))
  }
  return lines.join('\n')
}

const DATASET_CSV_HEADERS = [
  'local_fixture_id',
  'provider_fixture_id',
  'competition_id',
  'country',
  'league_name',
  'kickoff',
  'home_team_id',
  'home_team',
  'away_team_id',
  'away_team',
  'row_feature_safe',
  'static_identity_status',
  'snapshot_time_status',
  'sample_size',
  'history_quality_tier',
  'core_feature_status',
  'xg_status',
  'xg_source',
  'xg_available_fields',
  'xg_missing_fields',
  'xg_exclusion_reasons',
  'home_goals_scored_avg',
  'away_goals_scored_avg',
  'home_goals_scored_rolling_5',
  'away_goals_scored_rolling_5',
  'home_goals_scored_rolling_10',
  'away_goals_scored_rolling_10',
  'home_xg_for_avg',
  'away_xg_for_avg',
  'pair_xg_for_avg',
  'home_goals_conceded_avg',
  'away_goals_conceded_avg',
  'home_clean_sheet_freq',
  'away_clean_sheet_freq',
  'home_xg_against_avg',
  'away_xg_against_avg',
  'pair_xg_against_avg',
  'over_2_5_frequency_last_10',
  'gg_frequency_last_10',
  'total_goals_avg',
  'total_goals_rolling_5',
  'total_goals_rolling_10',
  'goals_ge_2_frequency_last_10',
  'goals_ge_3_frequency_last_10',
  'pair_goals_scored_rolling_5',
  'pair_goals_scored_rolling_10',
  'goals_scored_std_last_10',
  'goals_scored_mad_last_10',
  'goals_scored_cv_last_10',
  'goals_rolling_5_vs_10_delta',
  'goals_home_ft',
  'goals_away_ft',
  'total_goals_ft',
  'goals_ge_2',
  'goals_ge_3',
  'btts_ft',
  'kickoff_month',
  'chronological_index',
  'temporal_fold_candidate',
  'train_candidate',
  'validation_candidate',
  'test_candidate',
] as const

export function buildGoalIntensityDatasetCsvFilename(
  kind: 'all' | 'core_min5' | 'core_min10' | 'xg_paired',
  dateFrom: string,
  dateTo: string,
): string {
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  const map = {
    all: 'dataset_all',
    core_min5: 'dataset_core_min5',
    core_min10: 'dataset_core_min10',
    xg_paired: 'dataset_xg_paired',
  } as const
  return `cecchino_goal_intensity_v5_${map[kind]}_${from}_${to}.csv`
}

export function buildGoalIntensityDatasetSummaryJsonFilename(
  dateFrom: string,
  dateTo: string,
): string {
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  return `cecchino_goal_intensity_v5_dataset_summary_${from}_${to}.json`
}

export function datasetRowsToCsv(rows: GoalIntensityDatasetRow[]): string {
  const lines = [DATASET_CSV_HEADERS.join(',')]
  for (const row of rows) {
    const cells = DATASET_CSV_HEADERS.map((h) => {
      const raw = row[h]
      if (Array.isArray(raw)) return escapeCsvCell(raw.join('|'))
      return escapeCsvCell(raw)
    })
    lines.push(cells.join(','))
  }
  return lines.join('\n')
}

export function filterDatasetRowsForExport(
  rows: GoalIntensityDatasetRow[],
  kind: 'all' | 'core_min5' | 'core_min10' | 'xg_paired',
): GoalIntensityDatasetRow[] {
  if (kind === 'all') return rows
  if (kind === 'core_min5') {
    return rows.filter(
      (r) => r.core_feature_status === 'available' && Number(r.sample_size ?? 0) >= 5,
    )
  }
  if (kind === 'core_min10') {
    return rows.filter(
      (r) => r.core_feature_status === 'available' && Number(r.sample_size ?? 0) >= 10,
    )
  }
  return rows.filter(
    (r) =>
      r.core_feature_status === 'available' &&
      Number(r.sample_size ?? 0) >= 1 &&
      r.xg_status === 'available',
  )
}

export function datasetSummaryExportPayload(dataset: GoalIntensityV5DatasetResponse): Record<string, unknown> {
  return {
    status: dataset.status,
    version: dataset.version,
    filters: dataset.filters,
    dataset_summary: dataset.dataset_summary,
    deduplication: dataset.deduplication,
    identity_diagnostics: {
      ...dataset.identity_diagnostics,
      identity_excluded_diagnostics: undefined,
    },
    exclusion_bias_report: dataset.exclusion_bias_report,
    history_quality: dataset.history_quality,
    xg_cohorts: dataset.xg_cohorts,
    paired_xg_readiness: {
      ...dataset.paired_xg_readiness,
      paired_fixture_ids: undefined,
      paired_core_without_xg: {
        ...(dataset.paired_xg_readiness?.paired_core_without_xg as object),
        targets: undefined,
      },
      paired_enriched_with_xg: {
        ...(dataset.paired_xg_readiness?.paired_enriched_with_xg as object),
        targets: undefined,
      },
    },
    feature_definitions: dataset.feature_definitions,
    warnings: dataset.warnings,
    performance: dataset.performance,
    rows_exported: (dataset.dataset_rows ?? []).length,
  }
}
