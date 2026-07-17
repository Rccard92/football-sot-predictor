import { adminPostJson } from './api'
import { sanitizeFilenameFragment } from './downloadJsonFile'

export type GoalIntensityV5AuditRequest = {
  date_from: string
  date_to: string
  competition_id?: number | null
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
  excluded_advanced_features: Array<Record<string, unknown>>
  anti_leakage: Record<string, unknown>
  api_availability: Record<string, unknown>
  legacy_dependencies: Record<string, unknown>
  potential_conflicts: Array<Record<string, unknown>>
  interpretative_questions: string[]
  implementation_recommendation: Record<string, unknown>
  warnings: string[]
  performance: Record<string, unknown>
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
  const escape = (v: unknown) => {
    const s = v == null ? '' : String(v)
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
    return s
  }
  const lines = [headers.join(',')]
  for (const row of rows) {
    lines.push(headers.map((h) => escape((row as Record<string, unknown>)[h])).join(','))
  }
  return lines.join('\n')
}
