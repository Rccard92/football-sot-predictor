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

export function getCecchinoLabOverview(): Promise<CecchinoLabOverview> {
  return requestJson('/api/cecchino-lab/overview')
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

export function getCecchinoLabDataset(id: number): Promise<CecchinoLabDataset & { imports: unknown[] }> {
  return requestJson(`/api/cecchino-lab/datasets/${id}`)
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

export const HISTORICAL_SCAN_PILOT_MAX_MATCHES = 200
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

export function getHistoricalScanSummary(runId: number): Promise<Record<string, unknown>> {
  return requestJson(`/api/cecchino-lab/historical-scans/${runId}/summary`)
}

export async function downloadHistoricalScanReport(
  runId: number,
  options?: {
    mode?: HistoricalReportMode
    competition?: string
    module?: HistoricalReportModule
  },
): Promise<void> {
  const base = getApiBase()
  const params = new URLSearchParams()
  params.set('mode', options?.mode ?? 'ai_summary')
  if (options?.competition) params.set('competition', options.competition)
  if (options?.module) params.set('module', options.module)
  const res = await fetch(
    `${base}/api/cecchino-lab/historical-scans/${runId}/report?${params.toString()}`,
  )
  if (!res.ok) {
    throw new AdminHttpError(res.status, `Download report fallito (${res.status})`, null)
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

export type HistoricalRunDashboardOverview = {
  run: {
    run_id: number
    season_label: string
    scope?: string | null
    status: string
    scan_version: string
    source_git_commit?: string | null
    source_git_commit_source?: string | null
    source_revision_status?: string | null
    started_at?: string | null
    completed_at?: string | null
    bookmaker_storico: string
    bookmaker_today_operativo: string
    is_partial_run?: boolean
    not_full_season_report?: boolean
    run_scope?: string | null
  }
  is_provisional: boolean
  data_as_of: string
  filters: HistoricalRunFilters
  kpis: Record<string, unknown>
  progress: Record<string, unknown>
  module_coverage: Record<string, HistoricalRunModuleCoverage>
  market_summary: Record<string, unknown>
  warnings: string[]
  active_eligible_sample?: number
}

export type HistoricalRunModuleCoverage = {
  complete: number
  partial: number
  unavailable: number
  coverage_pct: number
  warnings: string[]
  observation_status: string
}

export type HistoricalRunDashboardMarket = {
  market_key: string
  label: string
  period?: string | null
  line?: string | null
  sample_size: number
  wins: number
  losses: number
  hit_rate: number | null
  outcome_base_rate: number | null
  average_cecchino_probability: number | null
  median_cecchino_probability: number | null
  calibration_gap: number | null
  brier_score: number | null
  average_rating: number | null
  rating_available_count: number
  signal_active_count: number
  matches_with_signal: number
  real_quote_count: number
  derived_quote_count: number
  unavailable_quote_count: number
  average_real_odds: number | null
  average_derived_odds: number | null
  real_profit_1u: number
  real_roi_pct: number | null
  synthetic_profit_1u: number
  synthetic_roi_pct: number | null
  max_losing_streak: number
  competitions_count: number
  chronological_stability: unknown
  warnings: string[]
  confidence_status?: string
}

export type HistoricalRunRatingCell = {
  market_key: string
  rating_band: string
  sample_size: number
  wins: number
  losses: number
  hit_rate: number | null
  average_odds: number | null
  real_quote_count: number
  real_profit_1u: number
  real_roi_pct: number | null
  derived_quote_count: number
  synthetic_profit_1u: number
  synthetic_roi_pct: number | null
  competitions_count: number
  confidence_status: string
}

export type HistoricalRunPurchasabilityAnalytics = {
  run_id: number
  is_provisional: boolean
  bands: string[]
  distribution: Record<string, Record<string, unknown>>
  by_market: Array<Record<string, unknown>>
  by_competition: Array<Record<string, unknown>>
  rating_x_purchasability: Array<Record<string, unknown>>
  complete_count: number
  partial_count: number
  unavailable_count: number
  profile_sample_size: number
  execution_status: string
  observation_status: string
  note?: string
}

export type HistoricalRunSignalModelAnalytics = {
  model_key: string
  model_label: string
  model_short_label: string
  weights: Record<string, number>
  weights_version: string
  is_current_model: boolean
  signals_activated: number
  matches_with_signal: number
  wins: number
  losses: number
  hit_rate: number | null
  real_quote_count: number
  real_profit: number
  real_roi: number | null
  derived_quote_count: number
  synthetic_profit: number
  synthetic_roi: number | null
  average_odds: number | null
  max_losing_streak: number
  market_best: string | null
  market_worst: string | null
  competition_best: string | null
  competition_worst: string | null
}

export type HistoricalRunBalanceAnalytics = {
  run_id: number
  pillars: Array<Record<string, unknown>>
  combinations: Array<Record<string, unknown>>
  note?: string
}

export type HistoricalRunGoalIntensityAnalytics = {
  run_id: number
  components: Array<Record<string, unknown>>
  combinations: Array<Record<string, unknown>>
  note?: string
}

export type HistoricalRunCompetitionAnalytics = {
  competition_name: string
  country?: string | null
  processed: number
  eligible: number
  excluded: number
  errors: number
  coverage_pct: number
  markets_generated: number
  real_quote_coverage: number
  derived_quote_coverage: number
  best_market_by_real_roi: string | null
  worst_market_by_real_roi: string | null
  real_profit_by_market: Record<string, number>
  real_roi_by_market: Record<string, number | null>
  exclusions_by_reason: Record<string, number>
  module_coverage: Record<string, HistoricalRunModuleCoverage>
}

export type HistoricalRunTimelinePoint = {
  period_key: string
  period_label: string
  historical_date_from: string | null
  historical_date_to: string | null
  processed: number
  eligible: number
  excluded: number
  hit_rate: number | null
  average_rating: number | null
  average_purchasability: number | null
  signals_count: number
  balance_coverage: number
  goal_intensity_coverage: number
  real_profit_by_market: Record<string, number>
  real_roi_by_market: Record<string, number | null>
}

export type HistoricalRunPattern = {
  pattern_id: string
  title?: string
  conditions: Record<string, unknown>
  sample_size: number
  wins: number
  losses: number
  hit_rate: number | null
  real_quote_count: number
  real_profit: number
  real_roi: number | null
  derived_quote_count: number
  synthetic_profit: number
  synthetic_roi: number | null
  competitions_count: number
  main_competition?: string | null
  main_competition_share?: number | null
  stability?: Record<string, unknown> | null
  status: string
  limitations: string[]
}

export type HistoricalRunExclusion = {
  reason_code: string
  label: string
  total: number
  percentage: number
  competitions: string[]
  chronological_distribution: Record<string, number>
  first_occurrence: string | null
  last_occurrence: string | null
  related_module: string
  is_expected: boolean
  is_data_quality_problem: boolean
}

export type HistoricalRunMatchRow = {
  snapshot_id: number
  lab_match_id: number
  date: string | null
  competition: string
  home_team: string | null
  away_team: string | null
  result: Record<string, unknown>
  eligibility: string
  exclusion_reason: string | null
  highest_rating_market: string | null
  highest_rating: number | null
  purchasability_summary: Record<string, unknown>
  active_signal_models: string[]
  balance_class: string
  goal_intensity_status: string
  quote_coverage: { real: number; derived: number; total: number }
  won_markets: string[]
  lost_markets: string[]
}

export type HistoricalRunMatchDetail = {
  run_id: number
  snapshot_id: number
  identity: Record<string, unknown>
  prematch: Record<string, unknown>
  result_after_lock: Record<string, unknown>
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

function dashboardGet<T>(path: string, filters: HistoricalRunFilters): Promise<T> {
  return requestJson(`${path}${historicalRunFiltersToQuery(filters)}`)
}

export function getHistoricalRunDashboardOverview(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunDashboardOverview> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/overview`, filters)
}

export function getHistoricalRunDashboardMarkets(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{ markets: HistoricalRunDashboardMarket[]; note?: string }> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/markets`, filters)
}

export function getHistoricalRunDashboardRatings(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{ bands: string[]; matrix: HistoricalRunRatingCell[]; note?: string }> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/ratings`, filters)
}

export function getHistoricalRunDashboardPurchasability(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunPurchasabilityAnalytics> {
  return dashboardGet(
    `/api/cecchino-lab/historical-scans/${runId}/dashboard/purchasability`,
    filters,
  )
}

export function getHistoricalRunDashboardSignals(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{
  models: HistoricalRunSignalModelAnalytics[]
  current_model_key: string
  note?: string
}> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/signals`, filters)
}

export function getHistoricalRunDashboardBalance(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunBalanceAnalytics> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/balance`, filters)
}

export function getHistoricalRunDashboardGoalIntensity(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunGoalIntensityAnalytics> {
  return dashboardGet(
    `/api/cecchino-lab/historical-scans/${runId}/dashboard/goal-intensity`,
    filters,
  )
}

export function getHistoricalRunDashboardCompetitions(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{ competitions: HistoricalRunCompetitionAnalytics[]; note?: string }> {
  return dashboardGet(
    `/api/cecchino-lab/historical-scans/${runId}/dashboard/competitions`,
    filters,
  )
}

export function getHistoricalRunDashboardTimeline(
  runId: number,
  filters: HistoricalRunFilters = {},
  opts?: { granularity?: string; block_size?: number },
): Promise<{ points: HistoricalRunTimelinePoint[]; granularity: string; note?: string }> {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  if (opts?.granularity) params.set('granularity', opts.granularity)
  if (opts?.block_size != null) params.set('block_size', String(opts.block_size))
  const q = params.toString()
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/dashboard/timeline${q ? `?${q}` : ''}`,
  )
}

export function getHistoricalRunDashboardPatterns(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{
  positive: HistoricalRunPattern[]
  negative: HistoricalRunPattern[]
  watchlist: HistoricalRunPattern[]
  unstable: HistoricalRunPattern[]
  note?: string
}> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/patterns`, filters)
}

export function getHistoricalRunDashboardExclusions(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{ items: HistoricalRunExclusion[]; total_excluded: number; note?: string }> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/exclusions`, filters)
}

export function listHistoricalRunMatches(
  runId: number,
  filters: HistoricalRunFilters = {},
  opts?: { limit?: number; offset?: number; sort_by?: string; sort_order?: string },
): Promise<{
  items: HistoricalRunMatchRow[]
  total: number
  limit: number
  offset: number
}> {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  if (!params.has('eligibility_status')) params.set('eligibility_status', 'all')
  params.set('limit', String(opts?.limit ?? 50))
  params.set('offset', String(opts?.offset ?? 0))
  if (opts?.sort_by) params.set('sort_by', opts.sort_by)
  if (opts?.sort_order) params.set('sort_order', opts.sort_order)
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/matches?${params.toString()}`,
  )
}

export function getHistoricalRunMatchDetail(
  runId: number,
  snapshotId: number,
): Promise<HistoricalRunMatchDetail> {
  return requestJson(`/api/cecchino-lab/historical-scans/${runId}/matches/${snapshotId}`)
}

export const HISTORICAL_RUN_REPORT_MENU: Array<{
  mode: HistoricalReportMode
  module?: HistoricalReportModule
  label: string
  recommended?: boolean
  needsCompetition?: boolean
  sizeWarning?: boolean
}> = [
  { mode: 'ai_summary', label: 'Sintesi per ChatGPT', recommended: true },
  { mode: 'competition', label: 'Dettaglio per campionato', needsCompetition: true },
  { mode: 'module', module: 'signals', label: 'Dettaglio Segnali A–F' },
  { mode: 'module', module: 'balance', label: 'Dettaglio Balance / Equilibrio' },
  { mode: 'module', module: 'goal_intensity', label: 'Dettaglio Intensità Goal' },
  { mode: 'module', module: 'purchasability', label: 'Dettaglio Acquistabilità' },
  { mode: 'module', module: 'markets', label: 'Dettaglio mercati' },
  {
    mode: 'full_archive',
    label: 'Archivio tecnico completo',
    sizeWarning: true,
  },
]
