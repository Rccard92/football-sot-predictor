/** Client API Cecchino Lab — archivio storico Football-Data. */

import { AdminHttpError, requestJson } from './api'

const IMPORT_CONFIRM_TOKEN = 'IMPORT_CECCHINO_LAB_CSV'

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
  completeness: { complete: number; incomplete: number; complete_pct: number }
  is_empty: boolean
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

export type ImportMeta = {
  competition_name: string
  country: string
  season_label: string
  timezone: string
  division_code?: string
}

export function previewCecchinoLabCsv(file: File, meta: ImportMeta): Promise<CecchinoLabPreview> {
  const form = new FormData()
  form.append('file', file)
  form.append('competition_name', meta.competition_name)
  form.append('country', meta.country)
  form.append('season_label', meta.season_label)
  form.append('timezone', meta.timezone)
  if (meta.division_code) form.append('division_code', meta.division_code)
  return postFormData('/api/admin/cecchino-lab/imports/preview', form)
}

export function importCecchinoLabCsv(file: File, meta: ImportMeta): Promise<CecchinoLabImportResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('competition_name', meta.competition_name)
  form.append('country', meta.country)
  form.append('season_label', meta.season_label)
  form.append('timezone', meta.timezone)
  form.append('confirm', IMPORT_CONFIRM_TOKEN)
  if (meta.division_code) form.append('division_code', meta.division_code)
  return postFormData('/api/admin/cecchino-lab/imports', form)
}

export { IMPORT_CONFIRM_TOKEN }

/** Pure helpers for unit tests */
export function formatOdd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

export function qualityBadgeClass(status: string): string {
  if (status === 'complete') return 'lab-badge-ok'
  if (status === 'error' || status === 'poor') return 'lab-badge-err'
  if (status === 'warning' || status === 'partial') return 'lab-badge-warn'
  return 'lab-badge-muted'
}

export function isOverviewEmpty(overview: CecchinoLabOverview | null): boolean {
  return !overview || overview.is_empty === true
}
