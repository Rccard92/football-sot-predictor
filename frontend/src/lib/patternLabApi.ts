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
  is_canonical?: boolean
  is_legacy?: boolean
  quote_policy_version?: string | null
  source_revision_status?: string | null
  canonical_checks?: Record<string, boolean>
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
  score_acquisto_min?: number | null
  score_acquisto_max?: number | null
  vantaggio_prob_min?: number | null
  vantaggio_prob_max?: number | null
  signals_count_min?: number | null
  signals_count_max?: number | null
  /** Filtro esplicito su pre_signal_active (non sostituito da signals_count). */
  signal_active?: boolean | null
  signal_columns?: Record<string, string>
  consensus_status?: string | null
  consensus_yes_count_min?: number | null
  consensus_yes_count_max?: number | null
  balance_class?: string | null
  gap_coherence_score_min?: number | null
  gap_coherence_score_max?: number | null
  balance_pillar_filters?: Record<string, { min?: number; max?: number; class?: string }>
  goal_final_class?: string | null
  goal_composite_min?: number | null
  goal_composite_max?: number | null
  goal_pillar_filters?: Record<string, { min?: number; max?: number; class?: string }>
  purchasability_v36_min?: number | null
  purchasability_v36_max?: number | null
  /** Se true, max è esclusivo (score < max). Default false = inclusivo. */
  purchasability_v36_max_exclusive?: boolean | null
  purchasability_v36_class?: string | null
  purchasability_v36_status?: string | null
  purchasability_v36_gate_status?: string | null
  bet_builder_active?: boolean | null
  bet_builder_rank_min?: number | null
  bet_builder_rank_max?: number | null
  outcome?: string | null
  quote_type?: string | null
  date_from?: string | null
  date_to?: string | null
  eligibility?: string
  /** Default operativo true: solo MATCH+MARKET con evidenza KPI/Signals/V3.6. */
  market_informative?: boolean
}

export type PatternLabValidationEvent = {
  season: string
  phase: string
  result: string
  roi_pct?: number | null
}

export type PatternLabPreset = {
  id: string
  label: string
  description?: string
  status: string
  /** Derivato da status lato API; non canonico nel registry. */
  status_group?: string
  ui_badge?: string
  discovery_seasons?: string[]
  validation_seasons?: string[]
  validation_history?: PatternLabValidationEvent[]
  first_oos_season?: string | null
  flags?: Record<string, boolean> | null
  scientific_filters_sha256?: string
  performance_quote_policy?: string
  filters: PatternLabFilters
  notes?: string
}

/** Raggruppamento visuale da status (specchio del backend). */
export function derivePresetStatusGroup(status: string | null | undefined): string {
  const s = (status || '').trim()
  if (s === 'positive_oos_weakened') return 'positive_weak'
  if (s === 'initial_replica_followup_negative') return 'mixed'
  if (s.startsWith('failed_oos')) return 'failed_oos'
  if (s.startsWith('candidate_oos')) return 'candidate_new'
  if (s.startsWith('validated')) return 'positive_weak'
  return 'mixed'
}

export type PatternLabPresetsResponse = {
  registry_version: string
  performance_quote_policy_default?: string
  presets: PatternLabPreset[]
}

export type PatternLabSummary = {
  selections: number
  /** COUNT DB mercati eligible (universo storico, senza filtro informative). */
  selections_historical_total?: number
  wins: number
  losses: number
  void: number
  win_rate: number | null
  avg_quota: number | null
  avg_rating?: number | null
  avg_purchasability_v36?: number | null
  profit_1u: number
  roi: number | null
}

export type PatternLabBreakdownBucket = PatternLabSummary & { key: string }

export type PatternLabHistBucket = { key: string; count: number }

export type PatternLabModuleInsights = {
  kpi: {
    rating_bands: PatternLabHistBucket[]
    value_positive_count: number
    value_negative_count: number
    avg_edge_pct: number | null
    edge_sample_n: number
  }
  signals: {
    active_count: number
    active_rate: number | null
    count_distribution: PatternLabHistBucket[]
    excel_column_frequency: Record<string, number>
  }
  balance: {
    structural_class_distribution: PatternLabHistBucket[]
    avg_geometry: number | null
    geometry_sample_n: number
  }
  goal_v4_compat: {
    final_class_distribution: PatternLabHistBucket[]
    direction_distribution: PatternLabHistBucket[]
    avg_composite: number | null
    composite_sample_n: number
  }
  purchasability_v36: {
    class_distribution: PatternLabHistBucket[]
    score_bands: PatternLabHistBucket[]
  }
}

export type PatternLabQueryResponse = {
  meta: Record<string, unknown>
  summary: PatternLabSummary
  breakdown: {
    by_season: PatternLabBreakdownBucket[]
    by_competition: PatternLabBreakdownBucket[]
    by_market: PatternLabBreakdownBucket[]
  }
  module_insights?: PatternLabModuleInsights
  rows: Array<Record<string, unknown>>
}

export type PatternLabBetBuilderReplayResponse = {
  meta: Record<string, unknown>
  summary: PatternLabSummary
  breakdown: PatternLabQueryResponse['breakdown']
  module_insights?: PatternLabModuleInsights
  timeline_by_day: Array<{
    date: string
    selections: number
    wins: number
    losses: number
    profit_1u: number
    roi: number | null
  }>
}

export type PatternLabFilterOptions = {
  competitions: string[]
  markets: Array<{ key: string; label: string }>
  balance_classes: string[]
  goal_final_classes: string[]
  purchasability_v36_classes: string[]
  purchasability_v36_statuses: string[]
  purchasability_v36_gates: string[]
  consensus_statuses: string[]
  balance_pillars: Array<{ key: string; label: string }>
  goal_pillars: Array<{ key: string; label: string }>
  signal_columns: string[]
}

export async function listPatternLabRuns(params?: {
  season_label?: string
  include_pilots?: boolean
  include_legacy?: boolean
}): Promise<{ items: PatternLabRunItem[]; count: number }> {
  const q = new URLSearchParams()
  if (params?.season_label) q.set('season_label', params.season_label)
  if (params?.include_pilots) q.set('include_pilots', 'true')
  if (params?.include_legacy) q.set('include_legacy', 'true')
  const qs = q.toString()
  return requestJson(`/api/cecchino-lab/pattern-lab/runs${qs ? `?${qs}` : ''}`)
}

export async function fetchPatternLabFilterOptions(
  runIds: number[],
): Promise<PatternLabFilterOptions> {
  const q = new URLSearchParams()
  q.set('run_ids', runIds.join(','))
  return requestJson(`/api/cecchino-lab/pattern-lab/filter-options?${q.toString()}`)
}

export async function fetchPatternLabPresets(): Promise<PatternLabPresetsResponse> {
  return requestJson('/api/cecchino-lab/pattern-lab/presets')
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
