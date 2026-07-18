import { adminGetJson } from './api'

export type PurchasabilityAuditFilters = {
  date_from?: string
  date_to?: string
  competition_id?: number | null
  market_family?: string | null
  book_source?: string | null
}

export type PurchasabilityVariableRow = {
  canonical_name: string
  source_field: string | null
  source_model: string | null
  source_function: string | null
  persistence: string
  pre_match_available: boolean
  leakage_risk: string
  independence_class: string
  redundancy_note: string | null
  explainability: string
  source_quality: string
  audit_status: string
  motivation: string
}

export type PurchasabilityMarketRow = {
  raw_market_code: string
  canonical_market_family: string
  period: string
  line: number | null
  comparator_selections: string[]
  complement_selection: string | null
  opposition_status: string
  observed_rows?: number
  verified_pre_match_rows?: number
  model_complete_rows?: number
  core_complete_rows?: number
  core_rows?: number
  settled_core_rows?: number
  settled_rows?: number
  settlement_pct?: number
  timestamp_verified_pct?: number
  normalization_applicability?: string
  blocking_reasons?: string[]
  sample_size_warning?: string[]
  settlement_available?: boolean
  unsupported_reason?: string | null
}

export type PurchasabilityAuditResponse = {
  version: string
  dataset_version: string
  status: string
  elapsed_ms: number
  summary: {
    observed_rows: number
    pre_match_rows: number
    core_rows: number
    core_complete_rows?: number
    market_valid_rows?: number
    model_complete_rows?: number
    settled_core_rows: number
    excluded_rows: number
    unique_fixtures: number
    timestamp_verified_rows?: number
    timestamp_verified_pct?: number
    generic_updated_at_fallback_rows?: number
    post_kickoff_excluded_rows?: number
    bookmaker_names?: string[]
    odds_sources?: string[]
    markets_ready: string[]
    date_min: string | null
    date_max: string | null
    note: string
    snapshot_limitation?: string
  }
  cohorts?: Record<string, unknown>
  variable_registry: PurchasabilityVariableRow[]
  market_coverage: PurchasabilityMarketRow[]
  exclusions: Record<string, number>
  phase_2_readiness: {
    recommended_next_step?: string
    blocking_issues?: string[]
    markets_ready?: string[]
    core_dataset_rows?: number
    settled_core_rows?: number
    variables_independent_candidates?: string[]
    variables_benchmark_candidates?: string[]
    variables_redundant_candidates?: string[]
    variables_excluded?: string[]
    [key: string]: unknown
  }
  rating_dependency_map?: Record<string, unknown>
  input_redundancy?: {
    vif?: {
      status?: string
      reason?: string | null
      vif?: Record<string, number | null>
      infinite_variables?: string[]
    }
    [key: string]: unknown
  }
  no_db_writes?: boolean
  no_purchasability_formula?: boolean
}

export type PurchasabilityDatasetItem = {
  today_fixture_id: number
  home_team?: string | null
  away_team?: string | null
  raw_market_code?: string
  selection?: string
  odds?: number | null
  rating?: number | null
  edge?: number | null
  settlement_status?: string
  unit_stake_profit?: number | null
  opposition_status?: string
  is_core?: boolean
  canonical_row_key?: string
  [key: string]: unknown
}

export type PurchasabilityDatasetResponse = {
  version: string
  total: number
  limit: number
  offset: number
  items: PurchasabilityDatasetItem[]
}

export type PurchasabilityExportKind =
  | 'audit_summary'
  | 'variable_registry'
  | 'market_opposition_map'
  | 'market_coverage'
  | 'dataset'
  | 'exclusions'
  | 'rating_dependency_map'

function qs(filters: PurchasabilityAuditFilters & { status?: string; limit?: number; offset?: number }): string {
  const p = new URLSearchParams()
  if (filters.date_from) p.set('date_from', filters.date_from)
  if (filters.date_to) p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.market_family) p.set('market_family', filters.market_family)
  if (filters.book_source) p.set('book_source', filters.book_source)
  if (filters.status) p.set('status', filters.status)
  if (filters.limit != null) p.set('limit', String(filters.limit))
  if (filters.offset != null) p.set('offset', String(filters.offset))
  return p.toString()
}

export async function getPurchasabilityAudit(
  filters: PurchasabilityAuditFilters = {},
): Promise<PurchasabilityAuditResponse> {
  const q = qs(filters)
  return adminGetJson(`/api/admin/cecchino/research/purchasability/audit${q ? `?${q}` : ''}`)
}

export async function getPurchasabilityDataset(
  filters: PurchasabilityAuditFilters & { status?: string; limit?: number; offset?: number } = {},
): Promise<PurchasabilityDatasetResponse> {
  const q = qs({ limit: 50, offset: 0, ...filters })
  return adminGetJson(`/api/admin/cecchino/research/purchasability/dataset?${q}`)
}

export async function getPurchasabilityMarkets(
  filters: Pick<PurchasabilityAuditFilters, 'date_from' | 'date_to'> = {},
): Promise<{ version: string; markets: PurchasabilityMarketRow[] }> {
  const q = qs(filters)
  return adminGetJson(`/api/admin/cecchino/research/purchasability/markets${q ? `?${q}` : ''}`)
}

export const PURCHASABILITY_EXPORT_PATHS: Record<PurchasabilityExportKind, string> = {
  audit_summary: '/api/admin/cecchino/research/purchasability/export/audit_summary',
  variable_registry: '/api/admin/cecchino/research/purchasability/export/variable_registry',
  market_opposition_map: '/api/admin/cecchino/research/purchasability/export/market_opposition_map',
  market_coverage: '/api/admin/cecchino/research/purchasability/export/market_coverage',
  dataset: '/api/admin/cecchino/research/purchasability/export/dataset',
  exclusions: '/api/admin/cecchino/research/purchasability/export/exclusions',
  rating_dependency_map: '/api/admin/cecchino/research/purchasability/export/rating_dependency_map',
}

export function buildPurchasabilityExportUrl(
  kind: PurchasabilityExportKind,
  filters: PurchasabilityAuditFilters = {},
): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''
  const q = qs(filters)
  return `${base}${PURCHASABILITY_EXPORT_PATHS[kind]}${q ? `?${q}` : ''}`
}
