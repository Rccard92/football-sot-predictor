/** Client API Pattern Lab — analytics multi-run READ-ONLY. */

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

export type PatternLabRunItem = {
  run_id: number
  season_label: string
  status: string
  scan_version: string | null
  run_scope: string | null
  is_partial_run: boolean | null
  is_pilot: boolean
  matches_eligible_core: number | null
  matches_processed: number | null
  completed_at: string | null
  source_git_commit: string | null
}

export type PatternLabFilters = {
  competitions?: string[]
  market_keys?: string[]
  quote_min?: number | null
  quote_max?: number | null
  rating_min?: number | null
  rating_max?: number | null
  value?: boolean | null
  edge_min?: number | null
  edge_max?: number | null
  signals_count_min?: number | null
  signals_count_max?: number | null
  signal_columns?: Record<string, string>
  balance_class?: string | null
  gap_coherence_score_min?: number | null
  gap_coherence_score_max?: number | null
  goal_final_class?: string | null
  goal_composite_min?: number | null
  goal_composite_max?: number | null
  purchasability_v36_min?: number | null
  purchasability_v36_max?: number | null
  purchasability_v36_class?: string | null
  bet_builder_active?: boolean | null
  outcome?: string | null
  quote_type?: string | null
  eligibility?: string
}

export type PatternLabSummary = {
  selections: number
  wins: number
  losses: number
  void: number
  win_rate: number | null
  avg_quota: number | null
  profit_1u: number
  roi: number | null
}

export type PatternLabBreakdownBucket = PatternLabSummary & { key: string }

export type PatternLabQueryResponse = {
  meta: Record<string, unknown>
  summary: PatternLabSummary
  breakdown: {
    by_season: PatternLabBreakdownBucket[]
    by_competition: PatternLabBreakdownBucket[]
    by_market: PatternLabBreakdownBucket[]
  }
  rows: Array<Record<string, unknown>>
}

export type PatternLabBetBuilderReplayResponse = {
  meta: Record<string, unknown>
  summary: PatternLabSummary
  breakdown: PatternLabQueryResponse['breakdown']
  timeline_by_day: Array<{
    date: string
    selections: number
    wins: number
    losses: number
    profit_1u: number
    roi: number | null
  }>
}

export async function listPatternLabRuns(params?: {
  season_label?: string
  include_pilots?: boolean
}): Promise<{ items: PatternLabRunItem[]; count: number }> {
  const q = new URLSearchParams()
  if (params?.season_label) q.set('season_label', params.season_label)
  if (params?.include_pilots) q.set('include_pilots', 'true')
  const qs = q.toString()
  return requestJson(`/api/cecchino-lab/pattern-lab/runs${qs ? `?${qs}` : ''}`)
}

export async function queryPatternLab(body: {
  run_ids: number[]
  filters?: PatternLabFilters
  include_rows?: boolean
  page?: number
  page_size?: number
}): Promise<PatternLabQueryResponse> {
  return requestJson('/api/cecchino-lab/pattern-lab/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function fetchPatternLabBetBuilderReplay(body: {
  run_ids: number[]
  filters?: PatternLabFilters
}): Promise<PatternLabBetBuilderReplayResponse> {
  return requestJson('/api/cecchino-lab/pattern-lab/bet-builder-replay', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function downloadPatternLabDiscoveryExport(body: {
  run_ids: number[]
  mode: 'full_selected_runs' | 'current_filters'
  filters?: PatternLabFilters
  include_observational_only?: boolean
}): Promise<Blob> {
  const base = getApiBase()
  const res = await fetch(`${base}/api/cecchino-lab/pattern-lab/export-discovery`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Export failed (${res.status})`)
  }
  return res.blob()
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatNum(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}
