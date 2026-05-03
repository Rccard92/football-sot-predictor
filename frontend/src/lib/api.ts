/** Client HTTP verso il backend. Base URL da `VITE_API_BASE_URL` (senza trailing slash). */

export const DEFAULT_SEASON = Number(import.meta.env.VITE_DEFAULT_SEASON) || 2025

export type LeagueDashboardBlock = {
  id: number
  api_league_id: number
  name: string
  country: string | null
  logo_url: string | null
}

export type SeasonDashboardBlock = {
  id: number
  league_id: number
  year: number
  label: string | null
  is_current: boolean
}

export type DataCoverageBlock = {
  teams_imported: boolean
  fixtures_imported: boolean
}

export type IngestionRunSummary = {
  id: number
  source: string
  status: string
  records_processed: number
  error_message: string | null
  meta: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

/** Allineato a [`backend/app/schemas/dashboard.py`](SerieADashboardResponse). */
export type SerieADashboardResponse = {
  league: LeagueDashboardBlock | null
  season: SeasonDashboardBlock | null
  teams_total: number
  fixtures_total: number
  fixtures_completed: number
  fixtures_scheduled: number
  fixtures_live_or_unknown: number
  fixtures_with_team_stats: number
  team_stats_rows_total: number
  team_stats_coverage_pct: number
  sot_feature_rows_total: number
  sot_feature_expected_rows: number
  sot_feature_coverage_pct: number
  sot_predictions_total: number
  sot_predictions_expected: number
  sot_predictions_coverage_pct: number
  avg_expected_sot: number
  avg_prediction_confidence: number
  sot_backtests_total: number
  sot_backtests_expected: number
  sot_backtest_coverage_pct: number
  sot_backtest_mae: number
  sot_backtest_rmse: number
  sot_backtest_avg_expected_sot: number
  sot_backtest_avg_actual_sot: number
  last_ingestion_run: IngestionRunSummary | null
  data_coverage: DataCoverageBlock
}

export type SerieADataHealthResponse = {
  fixtures_completed: number
  fixtures_with_team_stats: number
  fixtures_missing_team_stats: number
  missing_fixture_ids?: number[]
  team_stats_rows_total: number
  team_stats_coverage_pct: number
}

export type IngestionRunsResponse = {
  runs: IngestionRunSummary[]
  total: number
}

export type SotPredictionsSeasonSummaryResponse = {
  season: number
  model_version: string
  feature_rows_total: number
  predictions_total: number
  coverage_pct: number
  avg_expected_sot: number
  min_expected_sot: number
  max_expected_sot: number
  avg_confidence_score: number
}

export type BacktestNumericSummaryResponse = {
  season: number
  model_version: string
  predictions_total: number
  backtests_total: number
  coverage_pct: number
  mae: number
  rmse: number
  avg_expected_sot: number
  avg_actual_sot: number
  avg_absolute_error: number
  max_absolute_error: number
}

export type BacktestByTeamRow = {
  team_id: number
  team_name: string
  predictions_count: number
  avg_expected_sot: number
  avg_actual_sot: number
  mae: number
  rmse: number
  max_absolute_error: number
}

export type BacktestByTeamListResponse = {
  season: number
  model_version: string
  teams: BacktestByTeamRow[]
}

export type BacktestBySideRow = {
  side: string
  predictions_count: number
  avg_expected_sot: number
  avg_actual_sot: number
  mae: number
  rmse: number
}

export type BacktestBySideListResponse = {
  season: number
  model_version: string
  sides: BacktestBySideRow[]
}

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error(
      'VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.',
    )
  }
  return String(raw).replace(/\/+$/, '')
}

function extractErrorMessage(body: unknown, statusText: string): string {
  if (body && typeof body === 'object') {
    const o = body as Record<string, unknown>
    if (typeof o.message === 'string') return o.message
    if (typeof o.detail === 'string') return o.detail
    if (Array.isArray(o.detail)) {
      const first = o.detail[0] as Record<string, unknown> | undefined
      if (first && typeof first.msg === 'string') return first.msg
    }
  }
  return statusText || 'Richiesta non riuscita'
}

async function requestJson<T>(path: string): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`)

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
    throw new Error(extractErrorMessage(body, res.statusText))
  }

  if (body && typeof body === 'object' && 'status' in body) {
    const st = (body as Record<string, unknown>).status
    if (st === 'error') {
      throw new Error(extractErrorMessage(body, 'Errore API'))
    }
  }

  return body as T
}

/** POST: non interpreta `status: error` nel body come eccezione se HTTP 2xx (allineato ai route admin). */
async function requestPostJson<T>(path: string, body: unknown = {}): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })

  const ct = res.headers.get('content-type') ?? ''
  let parsed: unknown = null
  if (ct.includes('application/json')) {
    try {
      parsed = await res.json()
    } catch {
      parsed = null
    }
  }

  if (!res.ok) {
    throw new Error(extractErrorMessage(parsed, res.statusText))
  }

  return parsed as T
}

export async function getDashboard(season: number): Promise<SerieADashboardResponse> {
  return requestJson<SerieADashboardResponse>(`/api/dashboard/serie-a/${season}`)
}

export async function getDataHealth(season: number): Promise<SerieADataHealthResponse> {
  return requestJson<SerieADataHealthResponse>(`/api/admin/data-health/serie-a/${season}`)
}

export async function getIngestionRuns(): Promise<IngestionRunsResponse> {
  return requestJson<IngestionRunsResponse>('/api/admin/ingest/runs')
}

export async function getPredictionSummary(
  season: number,
): Promise<SotPredictionsSeasonSummaryResponse> {
  return requestJson<SotPredictionsSeasonSummaryResponse>(
    `/api/predictions/sot/serie-a/${season}/summary`,
  )
}

export async function getBacktestSummary(season: number): Promise<BacktestNumericSummaryResponse> {
  return requestJson<BacktestNumericSummaryResponse>(
    `/api/backtest/sot/serie-a/${season}/summary`,
  )
}

export async function getBacktestByTeam(season: number): Promise<BacktestByTeamListResponse> {
  return requestJson<BacktestByTeamListResponse>(
    `/api/backtest/sot/serie-a/${season}/by-team`,
  )
}

export async function getBacktestBySide(season: number): Promise<BacktestBySideListResponse> {
  return requestJson<BacktestBySideListResponse>(
    `/api/backtest/sot/serie-a/${season}/by-side`,
  )
}

export async function runBuildSotFeatures(season: number): Promise<unknown> {
  return requestPostJson<unknown>(`/api/features/sot/serie-a/${season}/build`, {})
}

export async function runGenerateSotPredictions(season: number): Promise<unknown> {
  return requestPostJson<unknown>(`/api/predictions/sot/serie-a/${season}/generate`, {})
}

export async function runSotBacktest(season: number): Promise<unknown> {
  return requestPostJson<unknown>(`/api/backtest/sot/serie-a/${season}/run`, {})
}
