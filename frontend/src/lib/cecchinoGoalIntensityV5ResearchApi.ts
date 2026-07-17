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
