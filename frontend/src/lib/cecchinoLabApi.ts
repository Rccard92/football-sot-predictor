/** Client API Cecchino Lab — archivio storico Football-Data. */

import { AdminHttpError, requestJson } from './api'

const IMPORT_CONFIRM_TOKEN = 'IMPORT_CECCHINO_LAB_CSV'
const REPLACE_CONFIRM_TOKEN = 'REPLACE_CECCHINO_LAB_DATASET'

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error(
      'VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.',
    )
  }
  return String(raw).replace(/\/+$/, '')
}

export type CecchinoLabOverview = {
  competitions_count: number
  seasons_count: number
  datasets_count: number
  matches_total: number
  matches_complete: number
  matches_incomplete: number
  anomalies_total: number
  anomalies_errors: number
  anomalies_warnings: number
  bet365_1x2_coverage_pct: number
  bet365_ou25_coverage_pct: number
  competitions: string[]
  seasons: string[]
  countries: string[]
  recent_imports: Array<{
    id: number
    dataset_id: number
    source_filename: string
    status: string
    rows_imported: number
    rows_skipped: number
    warnings_count: number
    errors_count: number
    competition_name: string | null
    season_label: string | null
    created_at: string | null
  }>
  best_quality_datasets: CecchinoLabDataset[]
  worst_quality_datasets: CecchinoLabDataset[]
  datasets_status: CecchinoLabDatasetStatus[]
  completeness: { complete: number; incomplete: number; complete_pct: number }
  is_empty: boolean
}

export type CecchinoLabDatasetStatus = {
  id: number
  competition_name: string
  season_label: string
  matches_count: number
  bet365_1x2_coverage_pct?: number | null
  bet365_ou25_coverage_pct?: number | null
  errors_count: number
  warnings_count: number
  info_count: number
  data_quality_status: string
}

export type CecchinoLabDataset = {
  id: number
  dataset_key: string
  competition_name: string
  country: string
  division_code: string | null
  season_label: string
  matches_count: number
  data_quality_status: string
  status: string
  bet365_1x2_coverage_pct?: number | null
  bet365_ou25_coverage_pct?: number | null
  anomalies_count?: number
  last_import_at?: string | null
  last_import_id?: number | null
}

export type CecchinoLabMatch = {
  id: number
  dataset_id: number
  match_date: string | null
  match_time: string | null
  home_team: string | null
  away_team: string | null
  ft_home_goals: number | null
  ft_away_goals: number | null
  ft_result: string | null
  ht_home_goals: number | null
  ht_away_goals: number | null
  ht_result: string | null
  bet365_home: number | null
  bet365_draw: number | null
  bet365_away: number | null
  bet365_over_25: number | null
  bet365_under_25: number | null
  row_quality_status: string
  competition_name: string | null
  season_label: string | null
  country: string | null
  bet365_1x2_pre_ready?: boolean
  bet365_ou25_pre_ready?: boolean
  statistics_ready?: boolean
  result_ft_ready?: boolean
}

export type CecchinoLabMatchDetail = CecchinoLabMatch & {
  referee: string | null
  home_shots: number | null
  away_shots: number | null
  home_shots_on_target: number | null
  away_shots_on_target: number | null
  home_fouls: number | null
  away_fouls: number | null
  home_corners: number | null
  away_corners: number | null
  home_yellow_cards: number | null
  away_yellow_cards: number | null
  home_red_cards: number | null
  away_red_cards: number | null
  bet365_closing_home: number | null
  bet365_closing_draw: number | null
  bet365_closing_away: number | null
  bet365_closing_over_25: number | null
  bet365_closing_under_25: number | null
  asian_handicap_home_line: number | null
  bet365_ah_home: number | null
  bet365_ah_away: number | null
  asian_handicap_closing_home_line: number | null
  bet365_closing_ah_home: number | null
  bet365_closing_ah_away: number | null
  odds_movement: Record<string, { pre: number | null; closing: number | null }>
  raw_json: Record<string, unknown> | null
  issues: Array<{
    id: number
    severity: string
    issue_code: string
    field_name: string | null
    message: string
    raw_value: string | null
  }>
}

export type CecchinoLabPreview = {
  source_filename: string | null
  headers: string[]
  recognized_columns: string[]
  missing_required_columns: string[]
  unexpected_columns: string[]
  rows_total: number
  preview_rows: Record<string, string | null>[]
  bet365_coverage: Record<string, number>
  warnings_count: number
  errors_count: number
  info_count?: number
  issues: Array<{
    severity: string
    issue_code: string
    message: string
    source_row_number: number | null
  }>
  summary: {
    importable: boolean
    rows_importable?: number
    rows_skipped?: number
  }
  file_sha256: string
  file_size_bytes: number
}

export type CecchinoLabImportResult = {
  status: string
  import_id: number
  dataset_id: number
  dataset_key: string
  rows_total: number
  rows_imported: number
  rows_skipped: number
  warnings_count: number
  errors_count: number
}

export type CecchinoLabIssue = {
  id: number
  import_id: number
  dataset_id: number
  match_id: number | null
  source_row_number: number | null
  severity: string
  issue_code: string
  field_name: string | null
  message: string
  raw_value: string | null
  created_at: string | null
  competition_name?: string | null
  season_label?: string | null
  country?: string | null
}

/** Metriche analytics Overview betting */
export type CecchinoLabMetricCount = {
  count: number
  percentage: number | null
  denominator: number
  numerator?: number
  sample_size?: number
}

export type CecchinoLabOutcomeMetric = CecchinoLabMetricCount & {
  average_bet365_pre_odds: number | null
  flat_profit_units: number | null
  flat_roi_pct: number | null
}

export type CecchinoLabGoalMetric = CecchinoLabMetricCount & {
  average_bet365_pre_odds?: number | null
  flat_profit_units?: number | null
  flat_roi_pct?: number | null
}

export type CecchinoLabFavoriteBucket = {
  bucket: string
  matches: number
  average_odds: number | null
  normalized_implied_probability: number | null
  actual_win_rate: number | null
  calibration_gap_pp: number | null
}

export type CecchinoLabLeagueRow = {
  competition_name: string
  country: string
  matches: number
  home_win_pct: number | null
  draw_pct: number | null
  away_win_pct: number | null
  over_25_pct: number | null
  under_25_pct: number | null
  btts_pct: number | null
  average_goals: number | null
  first_half_draw_pct: number | null
  favorite_hit_pct: number | null
  average_pre_margin_pct: number | null
  roi_home_pct: number | null
  roi_draw_pct: number | null
  roi_away_pct: number | null
  roi_over_25_pct: number | null
  roi_under_25_pct: number | null
  warnings_count: number
  errors_count: number
}

export type CecchinoLabInsight = {
  key: string
  title: string
  value: string
  description: string
  competition_name: string | null
  sample_size: number
  tone: 'positive' | 'neutral' | 'warning' | 'accent'
}

export type CecchinoLabAnalyticsFilters = {
  season_label?: string
  country?: string
  competition?: string
  dataset_id?: number
}

export type CecchinoLabQualityExportFilters = {
  format: 'csv' | 'json'
  scope: 'filtered' | 'all'
  severity?: string
  issue_code?: string
  dataset_id?: number
  competition?: string
  season_label?: string
}

export type CecchinoLabAnalyticsOverview = {
  available_filters: {
    seasons: string[]
    countries: string[]
    competitions: Array<{ name: string; country: string }>
  }
  applied_filters: {
    season_label: string | null
    country: string | null
    competition: string | null
    dataset_id: number | null
  }
  sample: {
    matches_total: number
    competitions_count: number
    seasons_count: number
  }
  summary: {
    matches_total: number
    competitions_count: number
    seasons_count: number
    total_goals: number
    average_goals_per_match: number | null
    average_home_goals: number | null
    average_away_goals: number | null
    favorite_hit_rate: number | null
    bet365_1x2_coverage_pct: number | null
    anomalies_errors: number
    anomalies_warnings: number
    completeness_pct: number | null
    best_flat_roi: { label: string; roi: number; sample_size: number } | null
    average_pre_closing_margin_pct: number | null
  }
  outcomes_1x2: {
    home: CecchinoLabOutcomeMetric
    draw: CecchinoLabOutcomeMetric
    away: CecchinoLabOutcomeMetric
  }
  goals: {
    over_15: CecchinoLabGoalMetric
    over_25: CecchinoLabGoalMetric
    under_25: CecchinoLabGoalMetric
    under_35: CecchinoLabGoalMetric
    btts_yes: CecchinoLabGoalMetric
    btts_no: CecchinoLabGoalMetric
    score_0_0: CecchinoLabGoalMetric
    team_blank: CecchinoLabGoalMetric
    goals_ge_4: CecchinoLabGoalMetric
    goals_ge_5: CecchinoLabGoalMetric
  }
  first_half: {
    draw: CecchinoLabMetricCount
    over_05: CecchinoLabMetricCount
    over_15: CecchinoLabMetricCount
    under_15: CecchinoLabMetricCount
    score_0_0: CecchinoLabMetricCount
    average_goals: number | null
    pct_of_ft_goals: number | null
    sample_size: number
  }
  favorite: {
    unique_count: number
    wins: number
    losses: number
    hit_rate: number | null
    average_odds: number | null
    home_favorite_pct: number | null
    away_favorite_pct: number | null
    draw_favorite_pct: number | null
    buckets: CecchinoLabFavoriteBucket[]
  }
  margins: {
    average_pre_closing_margin_pct: number | null
    median_pre_closing_margin_pct: number | null
    average_closing_margin_pct: number | null
    median_closing_margin_pct: number | null
    average_pre_to_closing_delta_pp: number | null
    by_competition: Array<{
      competition_name: string
      average_pre_closing_margin_pct: number | null
      sample_size: number
    }>
    sample_size_pre: number
    sample_size_closing: number
  }
  odds_movement: {
    average_home_movement_pct: number | null
    average_draw_movement_pct: number | null
    average_away_movement_pct: number | null
    favorite_shortened_pct: number | null
    winning_selection_shortened_pct: number | null
    average_winner_movement_pct: number | null
    sample_size: number
    distribution: Array<{ bucket: string; count: number; percentage: number | null }>
  }
  longest_odds_hit: {
    count: number
    percentage: number | null
    average_winning_odds: number | null
    top_competition: {
      competition_name: string
      percentage: number | null
      sample_size: number
    } | null
    record_match: {
      match_id: number
      match_date: string | null
      competition_name: string
      season_label: string
      home_team: string | null
      away_team: string | null
      result: string
      selection: string
      odds: number | null
    } | null
    sample_size: number
  }
  leagues: CecchinoLabLeagueRow[]
  insights: CecchinoLabInsight[]
  is_empty: boolean
}


async function postFormData<T>(path: string, form: FormData): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`, { method: 'POST', body: form })
  const ct = res.headers.get('content-type') ?? ''
  let body: unknown = null
  if (ct.includes('application/json')) {
    try {
      body = await res.json()
    } catch {
      body = null
    }
  }
  if (!res.ok) {
    throw new AdminHttpError(
      res.status,
      (body as { message?: string })?.message || res.statusText,
      body,
    )
  }
  if (body && typeof body === 'object' && 'status' in body && (body as { status: string }).status === 'error') {
    throw new AdminHttpError(
      res.status,
      (body as { message?: string }).message || 'Errore import',
      body,
    )
  }
  return body as T
}

async function postJson<T>(path: string, payload?: unknown): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  const ct = res.headers.get('content-type') ?? ''
  let body: unknown = null
  if (ct.includes('application/json')) {
    try {
      body = await res.json()
    } catch {
      body = null
    }
  }
  if (!res.ok) {
    throw new AdminHttpError(
      res.status,
      (body as { message?: string })?.message || res.statusText,
      body,
    )
  }
  if (body && typeof body === 'object' && 'status' in body && (body as { status: string }).status === 'error') {
    throw new AdminHttpError(
      res.status,
      (body as { message?: string }).message || 'Errore richiesta',
      body,
    )
  }
  return body as T
}

export function getCecchinoLabAnalyticsOverview(
  filters?: CecchinoLabAnalyticsFilters,
): Promise<CecchinoLabAnalyticsOverview> {
  const q = new URLSearchParams()
  if (filters?.season_label) q.set('season_label', filters.season_label)
  if (filters?.country) q.set('country', filters.country)
  if (filters?.competition) q.set('competition', filters.competition)
  if (filters?.dataset_id != null) q.set('dataset_id', String(filters.dataset_id))
  const qs = q.toString()
  return requestJson(`/api/cecchino-lab/analytics/overview${qs ? `?${qs}` : ''}`)
}

export async function downloadCecchinoLabQualityExport(
  filters: CecchinoLabQualityExportFilters,
): Promise<void> {
  const q = new URLSearchParams()
  q.set('format', filters.format)
  q.set('scope', filters.scope)
  if (filters.scope === 'filtered') {
    if (filters.severity) q.set('severity', filters.severity)
    if (filters.issue_code) q.set('issue_code', filters.issue_code)
    if (filters.dataset_id != null) q.set('dataset_id', String(filters.dataset_id))
    if (filters.competition) q.set('competition', filters.competition)
    if (filters.season_label) q.set('season_label', filters.season_label)
  }
  const base = getApiBase()
  const res = await fetch(`${base}/api/cecchino-lab/data-quality/issues/export?${q.toString()}`)
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
  const fallback = `cecchino_lab_quality.${filters.format === 'csv' ? 'csv' : 'json'}`
  const filename = match?.[1] || fallback
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}


export function getCecchinoLabDatasets(params?: {
  country?: string
  competition?: string
  season?: string
  quality_status?: string
}): Promise<{ items: CecchinoLabDataset[]; total: number }> {
  const q = new URLSearchParams()
  if (params?.country) q.set('country', params.country)
  if (params?.competition) q.set('competition', params.competition)
  if (params?.season) q.set('season', params.season)
  if (params?.quality_status) q.set('quality_status', params.quality_status)
  const qs = q.toString()
  return requestJson(`/api/cecchino-lab/datasets${qs ? `?${qs}` : ''}`)
}

export function getCecchinoLabMatches(params: Record<string, string | number | boolean | undefined>): Promise<{
  items: CecchinoLabMatch[]
  total: number
  page: number
  page_size: number
}> {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === '') continue
    q.set(k, String(v))
  }
  return requestJson(`/api/cecchino-lab/matches?${q.toString()}`)
}

export function getCecchinoLabMatch(id: number): Promise<CecchinoLabMatchDetail> {
  return requestJson(`/api/cecchino-lab/matches/${id}`)
}

export function getCecchinoLabIssues(params: Record<string, string | number | undefined>): Promise<{
  items: CecchinoLabIssue[]
  total: number
  page: number
  page_size: number
  top_issue_codes: Array<{ issue_code: string; count: number }>
  severity_counts: Record<string, number>
}> {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === '') continue
    q.set(k, String(v))
  }
  return requestJson(`/api/cecchino-lab/data-quality/issues?${q.toString()}`)
}

export type LabCompetitionCatalogItem = {
  key: string
  display_name: string
  country: string
  division_code: string
  timezone: string
}

export type ImportMeta = {
  competition_key: string
  season_label: string
}

export const LAB_SEASON_OPTIONS = [
  '2025/2026',
  '2024/2025',
  '2023/2024',
  '2022/2023',
  '2021/2022',
  '2020/2021',
] as const

export function getCecchinoLabCompetitions(): Promise<{ items: LabCompetitionCatalogItem[] }> {
  return requestJson('/api/cecchino-lab/catalog/competitions')
}

export function previewCecchinoLabCsv(file: File, meta: ImportMeta): Promise<CecchinoLabPreview> {
  const form = new FormData()
  form.append('file', file)
  form.append('competition_key', meta.competition_key)
  form.append('season_label', meta.season_label)
  return postFormData('/api/admin/cecchino-lab/imports/preview', form)
}

export type BatchImportStatus =
  | 'ready'
  | 'ready_with_warnings'
  | 'blocked'
  | 'already_imported'
  | 'duplicate_in_batch'
  | 'duplicate_competition_in_batch'
  | 'dataset_already_exists'

export type CecchinoLabBatchPreviewItem = {
  client_file_id: string
  filename: string
  file_sha256: string
  file_size_bytes: number
  division_code: string | null
  competition_key: string | null
  competition_name: string | null
  country: string | null
  timezone: string | null
  season_label: string
  rows_total: number | null
  rows_importable: number | null
  rows_skipped: number | null
  errors_count: number
  warnings_count: number
  info_count: number
  bet365_coverage: Record<string, number>
  mapping_status: string
  import_status: BatchImportStatus
  dataset_id: number | null
  blocking_reason: string | null
  issues: Array<{
    severity: string
    issue_code: string
    message: string
    source_row_number: number | null
  }>
  preview_rows: Record<string, string | null>[]
  recognized_columns: string[]
  unexpected_columns: string[]
  missing_required_columns: string[]
}

export type CecchinoLabBatchPreview = {
  status: string
  season_label: string
  files_total: number
  ready_count: number
  warning_count: number
  blocked_count: number
  already_imported_count: number
  rows_total: number
  rows_importable: number
  items: CecchinoLabBatchPreviewItem[]
}

export function previewCecchinoLabBatch(
  files: File[],
  seasonLabel: string,
): Promise<CecchinoLabBatchPreview> {
  const form = new FormData()
  form.append('season_label', seasonLabel)
  for (const file of files) {
    form.append('files', file)
  }
  return postFormData('/api/admin/cecchino-lab/imports/batch/preview', form)
}

export function batchImportStatusLabel(status: BatchImportStatus | string): string {
  switch (status) {
    case 'ready':
      return 'Pronto'
    case 'ready_with_warnings':
      return 'Pronto con warning'
    case 'already_imported':
      return 'Già importato'
    case 'duplicate_in_batch':
    case 'duplicate_competition_in_batch':
      return 'Duplicato'
    case 'dataset_already_exists':
      return 'Già presente'
    case 'blocked':
      return 'Bloccato'
    default:
      if (status === 'unknown_division' || status === 'missing_division') return 'Divisione sconosciuta'
      return status || '—'
  }
}

export function batchImportStatusBadgeClass(status: BatchImportStatus | string): string {
  if (status === 'ready') return 'lab-badge-ok'
  if (status === 'ready_with_warnings') return 'lab-badge-warn'
  if (status === 'already_imported' || status === 'dataset_already_exists') return 'lab-badge-muted'
  if (
    status === 'duplicate_in_batch' ||
    status === 'duplicate_competition_in_batch' ||
    status === 'blocked'
  ) {
    return 'lab-badge-err'
  }
  return 'lab-badge-muted'
}

export function isBatchItemReady(status: BatchImportStatus | string): boolean {
  return status === 'ready' || status === 'ready_with_warnings'
}

export function countBatchReadyItems(items: Array<{ import_status: string }>): number {
  return items.filter((i) => isBatchItemReady(i.import_status)).length
}

export function importCecchinoLabCsv(file: File, meta: ImportMeta): Promise<CecchinoLabImportResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('competition_key', meta.competition_key)
  form.append('season_label', meta.season_label)
  form.append('confirm', IMPORT_CONFIRM_TOKEN)
  return postFormData('/api/admin/cecchino-lab/imports', form)
}

export type CecchinoLabReplaceResult = {
  status: string
  dataset_id: number
  dataset_key: string
  competition_name: string
  season_label: string
  previous_matches_count: number
  import_id: number
  rows_total: number
  rows_imported: number
  rows_skipped: number
  warnings_count: number
  errors_count: number
  info_count: number
  data_quality_status: string
}

export function replaceCecchinoLabDataset(datasetId: number, file: File): Promise<CecchinoLabReplaceResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('confirm', REPLACE_CONFIRM_TOKEN)
  return postFormData(`/api/admin/cecchino-lab/datasets/${datasetId}/replace`, form)
}

export const HISTORICAL_SCAN_CONFIRM_TOKEN = 'RUN_CECCHINO_LAB_HISTORICAL_SCAN'
export const DEFAULT_HISTORICAL_SEASON = '2021/2022'

export type HistoricalScanPreflight = {
  season_label: string
  status: 'ready' | 'ready_with_warnings' | 'blocked' | string
  datasets_found: Array<{
    id: number
    dataset_key: string
    competition_name: string
    country: string
    matches_count: number
    data_quality_status: string
  }>
  competitions_found: string[]
  matches_total: number
  matches_with_valid_kickoff?: number
  matches_with_ft?: number
  matches_with_ht?: number
  bet365_1x2_pre_coverage?: number
  bet365_1x2_closing_coverage?: number
  bet365_ou25_pre_coverage?: number
  bet365_ou25_closing_coverage?: number
  quote_counts?: { real: number; derived: number; not_available: number }
  quote_policy_version?: string
  quote_reference_pre_only?: boolean
  scan_version?: string | null
  feature_contract_version?: string | null
  blocking_anomalies?: Array<{ code: string; message: string }>
  warnings?: Array<{ code: string; message: string }>
  module_availability?: Record<string, { status: string; note?: string }>
  market_availability?: Record<string, { status: string; expected_coverage_pct?: number }>
}

export type HistoricalScanRun = {
  id: number
  season_label: string
  status: string
  scan_version: string
  requested_at: string | null
  started_at: string | null
  completed_at: string | null
  current_dataset_id: number | null
  current_match_id: number | null
  current_competition: string | null
  matches_total: number
  matches_processed: number
  matches_eligible_core: number
  matches_excluded: number
  matches_error: number
  progress_pct: number | null
  progress_detail?: {
    competitions_completed?: number
    competitions_total?: number
    eligible_collected?: number
    eligible_target?: number
    matches_processed?: number
    matches_excluded?: number
    matches_error?: number
    current_competition?: string | null
    eligible_in_current_competition?: number | null
    eligible_per_competition_target?: number | null
  } | null
  preflight?: HistoricalScanPreflight | null
  summary?: Record<string, unknown> | null
  error?: Record<string, unknown> | null
  source_git_commit?: string | null
  source_git_commit_source?: string | null
  source_revision_status?: string | null
  cancel_requested?: boolean
  run_scope?: 'pilot' | 'balanced_pilot' | 'full' | string
  is_partial_run?: boolean
  not_full_season_report?: boolean
  max_matches?: number | null
  pilot_strategy?: string | null
  eligible_per_competition?: number | null
  module_policy?: Record<string, unknown> | null
}

export function preflightHistoricalScan(seasonLabel: string): Promise<HistoricalScanPreflight> {
  return postJson('/api/admin/cecchino-lab/historical-scans/preflight', {
    season_label: seasonLabel,
  })
}

export const HISTORICAL_SCAN_PILOT_MAX_MATCHES = 400
export const HISTORICAL_SCAN_BALANCED_ELIGIBLE_PER_COMP = 20

export type HistoricalReportMode =
  | 'ai_summary'
  | 'competition'
  | 'module'
  | 'full_archive'

export type HistoricalReportModule =
  | 'markets'
  | 'signals'
  | 'goal_intensity'
  | 'purchasability'
  | 'balance'

export function startHistoricalScan(
  seasonLabel: string,
  options?: {
    maxMatches?: number | null
    pilotStrategy?: 'max_matches' | 'eligible_per_competition' | null
    eligiblePerCompetition?: number | null
  },
): Promise<HistoricalScanRun> {
  const body: Record<string, unknown> = {
    season_label: seasonLabel,
    confirm: HISTORICAL_SCAN_CONFIRM_TOKEN,
  }
  if (options?.pilotStrategy) {
    body.pilot_strategy = options.pilotStrategy
  }
  if (options && 'eligiblePerCompetition' in (options || {})) {
    body.eligible_per_competition = options.eligiblePerCompetition ?? null
  }
  if (options && 'maxMatches' in options) {
    body.max_matches = options.maxMatches ?? null
  }
  return postJson('/api/admin/cecchino-lab/historical-scans', body)
}

export function historicalScanScopeLabel(run: HistoricalScanRun): string {
  if (run.run_scope === 'balanced_pilot' || run.pilot_strategy === 'eligible_per_competition') {
    const n = run.eligible_per_competition ?? HISTORICAL_SCAN_BALANCED_ELIGIBLE_PER_COMP
    return `Pilota bilanciato (${n} eleggibili/campionato)`
  }
  if (run.is_partial_run || run.run_scope === 'pilot') {
    const n = run.max_matches ?? HISTORICAL_SCAN_PILOT_MAX_MATCHES
    return `Test tecnico (max ${n})`
  }
  return 'Completa'
}

export function listHistoricalScans(seasonLabel?: string): Promise<HistoricalScanRun[]> {
  const q = seasonLabel ? `?season_label=${encodeURIComponent(seasonLabel)}` : ''
  return requestJson(`/api/cecchino-lab/historical-scans${q}`)
}

export function getHistoricalScan(runId: number): Promise<HistoricalScanRun> {
  return requestJson(`/api/cecchino-lab/historical-scans/${runId}`)
}

export function resumeHistoricalScan(runId: number): Promise<HistoricalScanRun> {
  return postJson(`/api/admin/cecchino-lab/historical-scans/${runId}/resume`)
}

export function cancelHistoricalScan(runId: number): Promise<HistoricalScanRun> {
  return postJson(`/api/admin/cecchino-lab/historical-scans/${runId}/cancel`)
}

async function readHttpErrorMessage(res: Response, fallback: string): Promise<string> {
  let message = fallback
  try {
    const body = (await res.json()) as {
      detail?: string | { message?: string; detail?: string }
      message?: string
    }
    if (typeof body?.detail === 'string') {
      message = body.detail
    } else if (body?.detail && typeof body.detail === 'object') {
      message =
        (typeof body.detail.message === 'string' && body.detail.message) ||
        (typeof body.detail.detail === 'string' && body.detail.detail) ||
        message
    } else if (typeof body?.message === 'string') {
      message = body.message
    }
  } catch {
    /* ignore non-JSON bodies */
  }
  return message
}

export function formatHistoricalDownloadError(err: unknown, fallback = 'Download fallito'): string {
  if (err instanceof AdminHttpError) {
    if (err.status === 409) {
      return (
        err.message ||
        'Acquistabilità V3 non disponibile: completa il replay prima di scaricare il report.'
      )
    }
    return err.message || fallback
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}

export async function downloadHistoricalScanReport(
  runId: number,
  options?: {
    mode?: HistoricalReportMode
    competition?: string
    module?: HistoricalReportModule
  },
): Promise<void> {
  if (options?.mode === 'module' && options.module === 'purchasability') {
    await downloadHistoricalRunOfficialPurchasabilityReport(runId, 'analysis')
    return
  }
  const base = getApiBase()
  const params = new URLSearchParams()
  params.set('mode', options?.mode ?? 'ai_summary')
  if (options?.competition) params.set('competition', options.competition)
  if (options?.module) params.set('module', options.module)
  const res = await fetch(
    `${base}/api/cecchino-lab/historical-scans/${runId}/report?${params.toString()}`,
  )
  if (!res.ok) {
    const message = await readHttpErrorMessage(
      res,
      `Download report fallito (${res.status})`,
    )
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="([^"]+)"/.exec(cd)
  const filename = match?.[1] || `cecchino_lab_ai_report_run_${runId}.zip`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function historicalScanStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: 'In coda',
    running: 'In esecuzione',
    completed: 'Completata',
    completed_with_warnings: 'Completata con warning',
    failed: 'Fallita',
    cancelled: 'Annullata',
    ready: 'Pronta',
    ready_with_warnings: 'Pronta con warning',
    blocked: 'Bloccata',
  }
  return map[status] || status
}

export function isHistoricalScanActive(status: string): boolean {
  return status === 'pending' || status === 'running'
}

export function quoteLegendClass(kind: 'real' | 'derived' | 'unavailable'): string {
  if (kind === 'real') return 'lab-quote-real'
  if (kind === 'derived') return 'lab-quote-derived'
  return 'lab-quote-na'
}

export { IMPORT_CONFIRM_TOKEN, REPLACE_CONFIRM_TOKEN }

/** Pure helpers for unit tests */
export function formatOdd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

/** Null / non calcolato → em dash (mai 0,00 fittizio). */
export function formatNullableNumber(
  v: number | null | undefined,
  digits = 2,
): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}

export function patternSampleBadgeLabel(status: string | null | undefined): string {
  switch (status) {
    case 'small_sample':
      return 'Campione insufficiente'
    case 'exploratory_only':
      return 'Esplorativo'
    case 'descriptive_only':
      return 'Descrittivo'
    case 'candidate_for_validation':
    case 'candidate_for_review':
      return 'Candidato da validare'
    case 'coverage_diagnostic':
      return 'Diagnostica copertura'
    default:
      return status || '—'
  }
}

export function patternStabilityBadgeLabel(
  category: string | null | undefined,
): string {
  switch (category) {
    case 'insufficient_evidence':
      return 'Insufficiente'
    case 'concentrated':
      return 'Concentrata'
    case 'inconsistent':
      return 'Incoerente'
    case 'directionally_consistent':
      return 'Coerente'
    case 'stable_candidate':
      return 'Candidata stabile'
    default:
      return category || '—'
  }
}

export function matchOddsColumnLabel(field: 'home' | 'draw' | 'away'): string {
  if (field === 'home') return '1'
  if (field === 'draw') return 'X'
  return '2'
}

export function qualityBadgeClass(status: string): string {
  if (status === 'complete') return 'lab-badge-ok'
  if (status === 'complete_with_warnings') return 'lab-badge-warn'
  if (status === 'error' || status === 'poor') return 'lab-badge-err'
  if (status === 'warning' || status === 'partial') return 'lab-badge-warn'
  return 'lab-badge-muted'
}

export function isOverviewEmpty(overview: CecchinoLabOverview | null): boolean {
  return !overview || overview.is_empty === true
}

export function formatAnomaliesHint(errors: number, warnings: number): string {
  return `${errors} errori · ${warnings} warning`
}

export function replaceDatasetConfirmMessage(
  competitionName: string,
  seasonLabel: string,
): string {
  return (
    `Stai per sostituire esclusivamente il CSV di ${competitionName} ${seasonLabel}. ` +
    `Serie A, Championship e gli altri dataset non saranno modificati.`
  )
}

/* ─── Historical run dashboard (read-only analytics) ─── */

export type HistoricalRunFilters = {
  competition?: string
  date_from?: string
  date_to?: string
  market_key?: string
  rating_band?: string
  purchasability_band?: string
  quote_quality?: string
  signal_model?: string
  signal_active?: string
  balance_class?: string
  goal_intensity_status?: string
  purchasability_status?: string
  eligibility_status?: string
}

/** Etichetta UI: mai «Molto Bassa» per gate rejected. */
export function purchasabilityGateDisplayLabel(
  gateStatus: string | null | undefined,
  scoreClass: string | null | undefined,
): string {
  if (gateStatus && String(gateStatus).startsWith('rejected_')) {
    return 'Bloccato dal gate'
  }
  if (gateStatus === 'accepted') {
    return scoreClass && scoreClass !== 'Molto Bassa' ? scoreClass : 'Accettato'
  }
  if (!gateStatus) return scoreClass || '—'
  return String(gateStatus)
}

export function historicalRunFiltersToQuery(filters: HistoricalRunFilters): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  const q = params.toString()
  return q ? `?${q}` : ''
}

export function parseHistoricalRunFiltersFromSearch(search: string): HistoricalRunFilters {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const out: HistoricalRunFilters = {}
  const keys: Array<keyof HistoricalRunFilters> = [
    'competition',
    'date_from',
    'date_to',
    'market_key',
    'rating_band',
    'purchasability_band',
    'quote_quality',
    'signal_model',
    'signal_active',
    'balance_class',
    'goal_intensity_status',
    'purchasability_status',
    'eligibility_status',
  ]
  for (const k of keys) {
    const v = params.get(k)
    if (v) out[k] = v
  }
  return out
}

export type HistoricalPurchasabilityV3ReplayIssueExample = {
  code?: string
  message?: string
  snapshot_id?: number
  market_key?: string
  competition_name?: string
  score_replay_status?: string
  performance_evaluation_status?: string
  [key: string]: string | number | boolean | null | undefined
}

export type HistoricalPurchasabilityV3ReplayMarketCoverage = {
  eligible_rows: number
  exact_replay_ready: number
  ready_with_warning: number
  gate_only_ready: number
  not_replayable: number
  invalid_integrity?: number
  invalid_pre_match_integrity?: number
  ambiguous_market_join?: number
  classified_total?: number
  unclassified?: number
  quote_real: number
  quote_derived: number
  quote_unavailable: number
  quote_inconsistent?: number
  performance_real_ready: number
  performance_synthetic_ready: number
  performance_result_without_profit?: number
  performance_not_applicable?: number
}

export type HistoricalPurchasabilityV3ReplayFamilyCoverage = {
  snapshots_with_full_family: number
  snapshots_with_partial_family: number
  snapshots_with_missing_family: number
  exact_replay_ready: number
  ready_with_warning: number
  not_replayable: number
  family_decisions_theoretical: number
}

export type HistoricalPurchasabilityV3ReplayProbeMarket = {
  submitted?: number
  returned?: number
  scored?: number
  gate_failed?: number
  unavailable?: number
  not_applicable?: number
  unsupported?: number
  errors?: number
  unclassified?: number
}

export type HistoricalPurchasabilityV3ReplayProbe = {
  skipped?: boolean
  reason?: string
  probe_is_diagnostic_only?: boolean
  probe_not_a_backtest?: boolean
  probe_snapshot_limit?: number
  snapshots_selected?: number
  snapshots_probed?: number
  markets_expected?: number
  panel_rows_submitted?: number
  formula_items_returned?: number
  markets_scored?: number
  markets_gate_failed?: number
  markets_unavailable?: number
  markets_not_applicable?: number
  markets_unsupported?: number
  markets_error?: number
  markets_unclassified?: number
  snapshots_with_error?: number
  probe_classified_total?: number
  expected_vs_returned_status?: string
  by_market?: Record<string, HistoricalPurchasabilityV3ReplayProbeMarket>
  errors?: Array<Record<string, string | number | null | undefined>>
  [key: string]: unknown
}

export type HistoricalPurchasabilityV3ReplayPreflight = {
  schema_version: string
  integrity_policy_version?: string
  status: 'ready' | 'ready_with_warnings' | 'blocked' | string
  generated_at: string
  cache_hit?: boolean
  run: {
    run_id: number
    season_label: string
    status: string
    run_scope?: string | null
    is_partial_run?: boolean
    not_full_season_report?: boolean
    completed_at?: string | null
    source_git_commit?: string | null
    source_revision_status?: string | null
    scan_version?: string
  }
  formula: {
    candidate_version: string
    formula_version: string
    audit_version: string
    runtime_git_commit?: string | null
    runtime_git_commit_source?: string | null
    historical_profile_used: boolean
    fixed_scales_used: boolean
  }
  bookmakers: {
    historical: string
    today_operational: string
    providers_are_different: boolean
    bookmaker_parity_status?: string
    formula_provider_dependency?: string
  }
  source_integrity: {
    snapshots_total?: number
    snapshots_eligible_core?: number
    snapshots_excluded?: number
    exclusions_by_reason?: Record<string, number>
    with_payload_hash?: number
    with_historical_freeze_lock?: number
    with_pre_match_hash?: number
    with_pre_match_lock?: number
    lock_before_kickoff?: number
    invalid_lock_timestamp?: number
    historical_reconstruction_verified?: number
    historical_reconstruction_with_warning?: number
    historical_reconstruction_invalid?: number
    chronological_lock_check_applicable?: number
    chronological_lock_check_passed?: number
    chronological_lock_check_failed?: number
    chronological_lock_check_not_applicable?: number
    duplicate_market_keys?: number
    snapshots_with_duplicates?: number
    formula_input_whitelist_verified?: boolean
    post_match_fields_excluded?: boolean
    score_performance_phase_separation_verified?: boolean
    integrity_mode_dominant?: string | null
    integrity_policy_version?: string
  }
  workload: {
    supported_markets_per_snapshot: number
    theoretical_evaluations: number
    market_rows_found?: number
    exact_replay_ready: number
    ready_with_warning: number
    gate_only_ready: number
    not_replayable: number
    invalid_integrity?: number
    ambiguous_market_join?: number
    classified_evaluations_total?: number
    unclassified_evaluations?: number
    family_decisions_theoretical?: number
  }
  quote_quality: {
    real: number
    derived: number
    unavailable: number
    inconsistent_flags: number
  }
  fair_probability_checks?: Record<string, number>
  performance_coverage: {
    real_profit_ready: number
    synthetic_profit_ready: number
    result_available_but_profit_missing: number
    not_applicable: number
  }
  by_market: Record<string, HistoricalPurchasabilityV3ReplayMarketCoverage>
  by_family?: Record<string, HistoricalPurchasabilityV3ReplayFamilyCoverage>
  by_competition?: Record<string, Record<string, number>>
  adapter_contract?: Record<string, unknown>
  anti_leakage?: {
    pre_match_input_fields?: string[]
    post_match_performance_fields?: string[]
    forbidden_formula_fields?: string[]
    formula_payload_allowed_fields?: string[]
    formula_payload_forbidden_fields_found?: string[]
    performance_fields_loaded_but_not_forwarded?: boolean
    anti_leakage_status?: string
    result_fields_passed_to_formula?: boolean
    settlement_fields_passed_to_formula?: boolean
  }
  probe?: HistoricalPurchasabilityV3ReplayProbe
  blockers: Array<{ code: string; message: string }>
  warnings: Array<{ code: string; message: string }>
  issue_examples?: Record<string, HistoricalPurchasabilityV3ReplayIssueExample[]>
  problematic_snapshots?: Array<Record<string, unknown>>
  replay_recommendation: {
    can_replay_without_full_scan: boolean
    requires_new_external_data: boolean
    requires_model_recalculation: boolean
    requires_database_migration: boolean
    recommended_next_action: string
  }
  status_rules?: Record<string, unknown>
  resource_profile?: {
    strategy?: string
    full_orm_entities_loaded?: boolean
    snapshot_json_fields_loaded?: boolean
    market_json_fields_loaded?: boolean
    market_rows_streamed?: number
    max_market_rows_held_in_memory?: number
    stream_yield_per?: number
    probe_requested?: boolean
    probe_snapshot_count?: number
    duration_ms?: number
    resource_budget_exceeded?: boolean
  }
  query_profile?: Record<string, number>
}

export function getHistoricalPurchasabilityV3ReplayPreflight(
  runId: number,
  opts?: { includeProbe?: boolean },
): Promise<HistoricalPurchasabilityV3ReplayPreflight> {
  const params = new URLSearchParams()
  if (opts?.includeProbe) params.set('include_probe', 'true')
  const q = params.toString()
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/purchasability-v3-replay/preflight${q ? `?${q}` : ''}`,
  )
}

export const PURCHASABILITY_V3_FORMULA_VERSION =
  'cecchino_purchasability_v3_fixed_discount_v1'
export const PURCHASABILITY_V3_PREFLIGHT_SCHEMA_VERSION =
  'cecchino_lab_purchasability_v3_replay_preflight_v2'
export const PURCHASABILITY_V3_INTEGRITY_POLICY_VERSION =
  'cecchino_lab_historical_reconstruction_integrity_v1'
export const PURCHASABILITY_V3_REPLAY_POLL_MS = 2500

export type PurchasabilityV3ReplayStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'cancel_requested'
  | 'cancelled'
  | 'failed'
  | 'interrupted'

export type PurchasabilityV3ReplayRun = {
  id: number
  source_scan_run_id: number
  status: PurchasabilityV3ReplayStatus | string
  effective_status?: PurchasabilityV3ReplayStatus | string
  replay_schema_version?: string
  replay_engine_version?: string
  candidate_version?: string
  formula_version?: string
  audit_version?: string
  preflight_schema_version?: string
  integrity_policy_version?: string
  requested_at?: string | null
  started_at?: string | null
  heartbeat_at?: string | null
  completed_at?: string | null
  snapshots_total?: number
  snapshots_processed?: number
  evaluations_total?: number
  evaluations_processed?: number
  results_persisted?: number
  progress_pct?: number | null
  current_snapshot_id?: number | null
  current_chronological_order?: number | null
  current_competition?: string | null
  scored_count?: number
  gate_failed_count?: number
  unavailable_count?: number
  not_applicable_count?: number
  error_count?: number
  unclassified_count?: number
  exact_source_count?: number
  warning_source_count?: number
  non_replayable_source_count?: number
  real_quote_count?: number
  derived_quote_count?: number
  unavailable_quote_count?: number
  cancel_requested?: boolean
  resume_count?: number
  attempt_count?: number
  idempotency_key?: string
  summary?: Record<string, unknown> | null
  error?: {
    error?: string
    message?: string
    details?: unknown
    phase?: string
    recoverable?: boolean
  } | null
  can_cancel?: boolean
  can_resume?: boolean
  reused_existing?: boolean
}

export function isPurchasabilityV3ReplayActive(status: string): boolean {
  return status === 'queued' || status === 'running' || status === 'cancel_requested'
}

export function startPurchasabilityV3Replay(
  runId: number,
  body: {
    confirmed: true
    expected_formula_version: string
    expected_preflight_schema_version: string
    expected_integrity_policy_version: string
  },
): Promise<PurchasabilityV3ReplayRun> {
  return postJson(
    `/api/admin/cecchino-lab/historical-scans/${runId}/purchasability-v3-replays`,
    body,
  )
}

export function getPurchasabilityV3Replay(replayId: number): Promise<PurchasabilityV3ReplayRun> {
  return requestJson(`/api/cecchino-lab/purchasability-v3-replays/${replayId}`)
}

export function cancelPurchasabilityV3Replay(
  replayId: number,
): Promise<PurchasabilityV3ReplayRun> {
  return postJson(`/api/admin/cecchino-lab/purchasability-v3-replays/${replayId}/cancel`)
}

export function resumePurchasabilityV3Replay(
  replayId: number,
): Promise<PurchasabilityV3ReplayRun> {
  return postJson(`/api/admin/cecchino-lab/purchasability-v3-replays/${replayId}/resume`)
}

export const PURCHASABILITY_V31_FORMULA_VERSION =
  'cecchino_purchasability_v31_fixed_discount_empirical_v2'
export const PURCHASABILITY_V31_PREFLIGHT_SCHEMA_VERSION =
  'cecchino_lab_purchasability_v31_replay_preflight_v2'
export const PURCHASABILITY_V31_INTEGRITY_POLICY_VERSION =
  'cecchino_lab_historical_reconstruction_integrity_v1'

export type PurchasabilityFormulaId = 'v3' | 'v31'

export function getHistoricalPurchasabilityReplayPreflight(
  runId: number,
  opts?: { includeProbe?: boolean; formulaVersion?: PurchasabilityFormulaId },
): Promise<HistoricalPurchasabilityV3ReplayPreflight> {
  const formula = opts?.formulaVersion || 'v3'
  if (formula === 'v3') {
    return getHistoricalPurchasabilityV3ReplayPreflight(runId, {
      includeProbe: opts?.includeProbe,
    })
  }
  const params = new URLSearchParams()
  params.set('formula_version', 'v31')
  if (opts?.includeProbe) params.set('include_probe', 'true')
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/purchasability-replay/preflight?${params}`,
  )
}

export function startPurchasabilityReplay(
  runId: number,
  body: {
    confirmed: true
    formula_version: PurchasabilityFormulaId
    expected_formula_version: string
    expected_preflight_schema_version: string
    expected_integrity_policy_version: string
  },
): Promise<PurchasabilityV3ReplayRun> {
  if (body.formula_version === 'v3') {
    return startPurchasabilityV3Replay(runId, {
      confirmed: true,
      expected_formula_version: body.expected_formula_version,
      expected_preflight_schema_version: body.expected_preflight_schema_version,
      expected_integrity_policy_version: body.expected_integrity_policy_version,
    })
  }
  return postJson(`/api/admin/cecchino-lab/historical-scans/${runId}/purchasability-replays`, body)
}

export function getPurchasabilityReplayAnalytics(
  replayId: number,
  formulaVersion: PurchasabilityFormulaId = 'v3',
): Promise<HistoricalPurchasabilityV3ReplayAnalytics & Record<string, unknown>> {
  if (formulaVersion === 'v3') {
    return getPurchasabilityV3ReplayAnalytics(replayId)
  }
  return requestJson(
    `/api/cecchino-lab/purchasability-replays/${replayId}/analytics?formula_version=v31`,
  )
}

export function getPurchasabilityV31Decision(
  replayId: number,
): Promise<Record<string, unknown>> {
  return requestJson(`/api/cecchino-lab/purchasability-replays/${replayId}/decision`)
}

export type HistoricalPurchasabilityV3ReplayPerformanceBucket = {
  stake_count: number
  profit_units: number | null
  roi_pct: number | null
  wins?: number
  losses?: number
  hit_rate_pct?: number | null
  average_odds?: number | null
  technical_aggregate_only?: boolean
  do_not_interpret_as_strategy?: boolean
  diagnostic_only?: boolean
  exclude_from_real_roi?: boolean
  not_a_real_bet365_quote?: boolean
}

export type HistoricalPurchasabilityV3ReplayReconciliation = {
  status: 'ok' | 'failed' | string
  all_evaluations?: number
  buckets?: Record<string, number>
  quote_buckets?: {
    real?: number
    derived?: number
    unavailable?: number
  }
  checks?: Array<{ code: string; ok: boolean; detail?: unknown }>
}

export type HistoricalPurchasabilityV3ReplayMarketAnalytics = {
  evaluations_total: number
  scored: number
  gate_failed: number
  unavailable: number
  real_quote?: number
  derived_quote?: number
  quote_type?: string
  performance_real?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  performance_synthetic?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  not_a_real_bet365_quote?: boolean
  exclude_from_real_roi?: boolean
}

export type HistoricalPurchasabilityV3ReplayPenaltyAnalytics = {
  descriptive_observational_analysis?: boolean
  fields?: Record<
    string,
    {
      count_available?: number
      count_applied?: number
      application_rate?: number | null
      mean?: number | null
      median?: number | null
    }
  >
  total_penalty_bands?: Record<string, number>
}

export type HistoricalPurchasabilityV3ReplayAnalytics = {
  schema_version: string
  status: 'ready' | 'ready_with_warnings' | 'blocked' | string
  generated_at?: string
  replay?: {
    replay_id?: number
    source_scan_run_id?: number
    status?: string
    formula_version?: string
    replay_schema_version?: string
  }
  universes?: {
    ALL_EVALUATIONS?: number
    SCORED_EVALUATIONS?: number
    GATE_FAILED_EVALUATIONS?: number
    UNAVAILABLE_EVALUATIONS?: number
    REAL_PERFORMANCE_UNIVERSE?: number
    SYNTHETIC_PERFORMANCE_UNIVERSE?: number
  }
  reconciliation?: HistoricalPurchasabilityV3ReplayReconciliation
  performance_real?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  performance_synthetic?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  by_market?: Record<string, HistoricalPurchasabilityV3ReplayMarketAnalytics>
  penalties?: HistoricalPurchasabilityV3ReplayPenaltyAnalytics
  warnings?: string[]
  blockers?: Array<{ code: string; message: string }>
  metadata?: {
    formula_recomputed?: boolean
    analytics_reads_persisted_replay?: boolean
    source_replay_id?: number
    source_replay_immutable?: boolean
    report_valid?: boolean
  }
  resource_profile?: {
    strategy?: string
    rows_read?: number
    formula_recomputed?: boolean
    duration_ms?: number
  }
}

export type PurchasabilityV3ReplayReportMode = 'analysis' | 'full_archive'

export async function downloadHistoricalRunOfficialPurchasabilityReport(
  runId: number,
  mode: PurchasabilityV3ReplayReportMode = 'analysis',
): Promise<void> {
  const base = getApiBase()
  const params = new URLSearchParams()
  params.set('mode', mode)
  const res = await fetch(
    `${base}/api/cecchino-lab/historical-scans/${runId}/purchasability/report?${params.toString()}`,
  )
  if (!res.ok) {
    const message = await readHttpErrorMessage(
      res,
      `Download report Acquistabilità V3 fallito (${res.status})`,
    )
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="([^"]+)"/.exec(cd)
  const filename = match?.[1] || `cecchino-run-${runId}-purchasability-v3.zip`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function getPurchasabilityV3ReplayAnalytics(
  replayId: number,
): Promise<HistoricalPurchasabilityV3ReplayAnalytics> {
  return requestJson(`/api/cecchino-lab/purchasability-v3-replays/${replayId}/analytics`)
}

export async function downloadPurchasabilityV3ReplayReport(
  replayId: number,
  mode: PurchasabilityV3ReplayReportMode = 'analysis',
): Promise<void> {
  const base = getApiBase()
  const params = new URLSearchParams()
  params.set('mode', mode)
  const res = await fetch(
    `${base}/api/cecchino-lab/purchasability-v3-replays/${replayId}/report?${params.toString()}`,
  )
  if (!res.ok) {
    let message = `Download report V3 fallito (${res.status})`
    try {
      const body = (await res.json()) as { detail?: string; message?: string }
      message = body?.detail || body?.message || message
    } catch {
      /* ignore */
    }
    if (res.status === 409) {
      message =
        'Il replay deve essere completato prima di generare analytics o report.'
    }
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="([^"]+)"/.exec(cd)
  const fallback =
    mode === 'full_archive'
      ? `cecchino-purchasability-v3-replay-${replayId}-full.zip`
      : `cecchino-purchasability-v3-replay-${replayId}-analysis.zip`
  const filename = match?.[1] || fallback
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/* ─── Historical KPI Signals (STEP 4A/4B) ─── */

/* ─── Historical Signals A–F (STEP 4B) ─── */

export const HISTORICAL_RUN_REPORT_MENU: Array<{
  mode: HistoricalReportMode
  module?: HistoricalReportModule
  label: string
  description?: string
  recommended?: boolean
  needsCompetition?: boolean
  sizeWarning?: boolean
}> = [
  { mode: 'ai_summary', label: 'Sintesi per ChatGPT', recommended: true },
  { mode: 'competition', label: 'Dettaglio per campionato', needsCompetition: true },
  { mode: 'module', module: 'signals', label: 'Dettaglio Segnali A–F' },
  { mode: 'module', module: 'balance', label: 'Dettaglio Balance / Equilibrio' },
  { mode: 'module', module: 'goal_intensity', label: 'Dettaglio Intensità Goal' },
  {
    mode: 'module',
    module: 'purchasability',
    label: 'Acquistabilità V3 legacy (replay)',
    description:
      'ZIP replay V3 legacy (diagnostico). L’indice corrente nel Pattern Lab / AI Summary è V3.6.',
  },
  { mode: 'module', module: 'markets', label: 'Dettaglio mercati' },
  {
    mode: 'full_archive',
    label: 'Archivio tecnico completo',
    sizeWarning: true,
  },
]

// ---------------------------------------------------------------------------
// Goal Intensity V4 vs V5 historical benchmark
// ---------------------------------------------------------------------------
