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

export function getCecchinoLabOverview(): Promise<CecchinoLabOverview> {
  return requestJson('/api/cecchino-lab/overview')
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
