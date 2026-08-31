/** Client API League Pattern Analysis — snapshot aggregato READ-ONLY. */

import { requestJson } from './api'

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error(
      'VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.',
    )
  }
  return String(raw).replace(/\/+$/, '')
}

export type LpaMetrics = {
  n?: number
  wins?: number
  losses?: number
  void?: number
  win_rate?: number | null
  avg_odds?: number | null
  profit_1u?: number
  roi?: number | null
  roi_pct?: number | null
  positive_seasons?: number
  seasons_with_bets?: number
  stability_label?: string
  best_season_roi_pct?: number | null
  worst_season_roi_pct?: number | null
}

export type LpaHuman = {
  human_title?: string
  short_explanation?: string
  long_explanation?: string
  structured_conditions?: Array<{ key: string; label: string; value: string }>
  technical_formula?: string
}

export type LpaSeasonCell = LpaMetrics & {
  season?: string
  season_short?: string
}

export type LpaPatternSummary = {
  pattern_id: string
  label?: string
  status?: string
  ui_badge?: string
  human?: LpaHuman
  scientific_filters_sha256?: string
  by_season?: Record<string, LpaSeasonCell>
  total?: LpaMetrics
  human_title?: string
  competition?: string
  discovery_seasons?: string[]
  internal_validation_seasons?: string[]
  first_true_oos_season?: string
}

export type LpaLatestPayload = {
  metadata: {
    snapshot_id: number
    analysis_version: string
    analysis_revision?: number
    status: string
    generated_at?: string | null
    source_run_ids: number[]
    source_seasons: string[]
    analysis_dataset_locked?: boolean
    future_oos_season?: string
    future_oos_included?: boolean
    preset_registry_version?: string
    source_git_commit?: string | null
  }
  summary: {
    seasons_count?: number
    competitions_count?: number
    eligible_matches_analyzed?: number
    informative_market_rows_analyzed?: number
    global_patterns_count?: number
    league_native_count?: number
    top_insights?: Record<string, unknown>
    analysis_dataset_locked?: boolean
    future_oos_included?: boolean
  }
  global_patterns: LpaPatternSummary[]
  competition_regimes_overview: Array<{
    competition: string
    total?: {
      matches?: number
      home_pct?: number | null
      draw_pct?: number | null
      away_pct?: number | null
      over_25_pct?: number | null
      under_25_pct?: number | null
      avg_ft_goals?: number | null
    }
  }>
  heatmap: {
    pattern_ids?: string[]
    competitions?: string[]
    cells?: Array<{
      pattern_id: string
      competition: string
      n: number
      roi_pct?: number | null
      profit_1u?: number
      positive_seasons?: number
      seasons_with_bets?: number
      worst_season_roi_pct?: number | null
      low_sample?: boolean
    }>
    low_sample_n?: number
  }
  specializations: Array<{
    id: string
    pattern_id: string
    competition: string
    status: string
    label: string
    metrics?: LpaMetrics & { by_season?: Record<string, LpaSeasonCell> }
  }>
  incompatibilities: Array<{
    id: string
    pattern_id: string
    competition: string
    status: string
    label: string
    metrics?: LpaMetrics & { by_season?: Record<string, LpaSeasonCell> }
    negative_seasons?: number
    negative_label?: string
  }>
  league_native: LpaPatternSummary[]
  methodology: Record<string, unknown>
}

export type LpaLeagueDetail = {
  metadata: LpaLatestPayload['metadata']
  competition: string
  league_overview: {
    competition: string
    by_season?: Record<string, Record<string, unknown>>
    total?: Record<string, unknown>
  }
  patterns: Array<{
    pattern_id: string
    label?: string
    human?: LpaHuman
    by_season?: Record<string, LpaSeasonCell>
    total?: LpaMetrics
  }>
}

export type LpaPatternDetail = {
  metadata: LpaLatestPayload['metadata']
  pattern: LpaPatternSummary & {
    filters?: Record<string, unknown>
    by_competition?: Record<
      string,
      { competition: string; by_season?: Record<string, LpaSeasonCell>; total?: LpaMetrics }
    >
  }
}

export async function fetchLeaguePatternAnalysisLatest(): Promise<LpaLatestPayload> {
  return requestJson(`${getApiBase()}/api/cecchino-lab/league-pattern-analysis/latest`)
}

export async function fetchLeaguePatternAnalysisLeague(
  competition: string,
): Promise<LpaLeagueDetail> {
  const enc = encodeURIComponent(competition)
  return requestJson(
    `${getApiBase()}/api/cecchino-lab/league-pattern-analysis/leagues/${enc}`,
  )
}

export async function fetchLeaguePatternAnalysisPattern(
  patternId: string,
): Promise<LpaPatternDetail> {
  return requestJson(
    `${getApiBase()}/api/cecchino-lab/league-pattern-analysis/patterns/${encodeURIComponent(patternId)}`,
  )
}

export async function fetchLeaguePatternAnalysisNative(
  patternId: string,
): Promise<LpaPatternDetail> {
  return requestJson(
    `${getApiBase()}/api/cecchino-lab/league-pattern-analysis/native/${encodeURIComponent(patternId)}`,
  )
}

export function formatRoiPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}%`
}

export function formatPct01(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(1)}%`
}

export function formatNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}
