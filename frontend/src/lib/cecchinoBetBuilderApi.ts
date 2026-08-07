/**
 * Client API Bet Builder BET-01 — contratti tipizzati + fetch opportunities.
 * UI Opportunity Board in BET-02; qui solo il contratto client.
 */

import { requestJson } from './api'

export type BetBuilderOrigin = 'price' | 'signals' | 'price_and_signals'

export type BetBuilderPriceValue = {
  present: boolean
  method: string
  quota_book: number | null
  quota_cecchino: number | null
  prob_book: number | null
  prob_cecchino: number | null
  vantaggio_prob: number | null
  edge_pct: number | null
  score_acquisto: number | null
  rating: number | null
  rating_label: string | null
  status: string | null
  book_source?: string | null
  cecchino_source?: string | null
}

export type BetBuilderSignalsEvidence = {
  available: boolean
  present: boolean
  formula_version?: string | null
  consensus_policy_version?: string | null
  evidence_mode?: string | null
  yes_count: number
  required_count: number
  available_count: number
  yes_columns: string[]
  passed: boolean
  consensus_exempt?: boolean
  source_group?: string
  reason?: string
}

export type BetBuilderPurchasabilityV31 = {
  available: boolean
  version?: string
  score: number | null
  raw_score?: number | null
  class?: string | null
  status?: string | null
  calculation_quality?: string | null
  gate_status?: string | null
  gate_reason_codes?: string[]
  formula_version?: string | null
  formula_config_version?: string | null
  candidate_version?: string | null
  candidate_name?: string | null
  registry_status?: string | null
  source_mode?: string | null
  generated_at?: string | null
  source_snapshot_at?: string | null
  source_snapshot_verified?: boolean | null
  source_snapshot_before_kickoff?: boolean | null
  historical_multiplier?: number | null
  historical_adjustment_points?: number | null
  historical_adjustment_pct?: number | null
  historical_reason_codes?: string[]
  market_key?: string
  market_label?: string | null
  market_family?: string | null
  period?: string | null
  line?: number | null
  reading_short?: string | null
  reading_detailed?: string | null
  reason_codes?: string[]
  warnings?: string[]
  reason?: string
}

export type BetBuilderBalancePillar = {
  index: number | null
  class_label: string | null
}

export type BetBuilderBalanceContextPayload = {
  status?: unknown
  version?: string | null
  snapshot_version?: string | null
  source_mode?: string | null
  pillar_order?: string[]
  pillars: {
    f36?: BetBuilderBalancePillar
    dominance?: BetBuilderBalancePillar
    draw_credibility?: BetBuilderBalancePillar
    gap_coherence?: BetBuilderBalancePillar
  }
  f36_index?: number | null
  dominance_index?: number | null
  draw_credibility_index?: number | null
  gap_coherence_index?: number | null
  prob_1_norm?: number | null
  prob_x_norm?: number | null
  prob_2_norm?: number | null
  snapshot_timestamp?: string | null
  pre_match_verified?: boolean | null
}

export type BetBuilderGoalIntensityContextPayload = {
  module_version?: string | null
  bundle_version?: string | null
  source?: string | null
  presentation?: string | null
  official?: boolean
  data_quality?: Record<string, unknown> | null
  raw_index?: string | null
  raw_index_score?: number | null
  expected_total_goals?: number | null
  expected_total_goals_calibration_source?: string | null
  probability_selection?: number | null
  probability_opposite?: number | null
  calibration_source?: string | null
  market_key?: string
}

export type BetBuilderContextSupport = {
  available: boolean
  module?: string | null
  status?: string
  reason?: string
  payload?: BetBuilderBalanceContextPayload | BetBuilderGoalIntensityContextPayload | null
}

export type BetBuilderOpportunity = {
  opportunity_key: string
  fixture: {
    today_fixture_id: number
    provider_fixture_id?: number | null
    scan_date?: string | null
    kickoff?: string | null
    country?: string | null
    league?: string | null
    home: { name?: string | null; logo?: string | null }
    away: { name?: string | null; logo?: string | null }
  }
  market: {
    market_key: string
    label: string
    family?: string | null
    period?: string | null
    line?: number | null
  }
  origin: BetBuilderOrigin
  price_value: BetBuilderPriceValue
  signals: BetBuilderSignalsEvidence
  purchasability_v31: BetBuilderPurchasabilityV31
  context_support: BetBuilderContextSupport
  freshness: {
    source_scan_date?: string
    fixture_updated_at?: string | null
    signals_updated_at?: string | null
    purchasability_v31_generated_at?: string | null
    context_snapshot_at?: string | null
  }
}

export type BetBuilderOpportunitiesSummary = {
  fixtures_considered: number
  fixtures_eligible_total?: number
  excluded_post_kickoff?: number
  opportunities_total: number
  price_only: number
  signals_only: number
  price_and_signals: number
  with_purchasability_v31: number
  without_purchasability_v31: number
  by_market: Record<string, number>
}

export type BetBuilderSourceGeneratedFrom = {
  scan_date?: string
  fixture_count?: number
  max_fixture_updated_at?: string | null
  max_purchasability_v31_generated_at?: string | null
  max_goal_intensity_snapshot_at?: string | null
  latest_scan_job?: {
    job_id?: string
    status?: string
    finished_at?: string | null
    updated_at?: string | null
    started_at?: string | null
  } | null
}

export type BetBuilderResponseFreshness = {
  source_scan_date?: string
  source_scan_status?: string | null
  freshness_warning?: string | null
  max_fixture_updated_at?: string | null
  max_purchasability_v31_generated_at?: string | null
  max_goal_intensity_snapshot_at?: string | null
}

export type BetBuilderOpportunitiesResponse = {
  contract_version: string
  aggregator_version: string
  signal_evidence_version?: string
  purchasability_policy_version?: string
  purchasability_policy: string
  scan_date: string
  source_revision: string
  source_generated_from?: BetBuilderSourceGeneratedFrom
  source_scan_status?: string | null
  freshness: BetBuilderResponseFreshness
  summary: BetBuilderOpportunitiesSummary
  opportunities: BetBuilderOpportunity[]
}

export type FetchBetBuilderOpportunitiesParams = {
  date: string
  market_key?: string
  origin?: BetBuilderOrigin
}

/** Chiavi mercato BET-01 (allineate al backend). */
export const BET_BUILDER_MARKET_KEYS = [
  'HOME',
  'DRAW',
  'AWAY',
  'ONE_X',
  'X_TWO',
  'ONE_TWO',
  'DRAW_PT',
  'OVER_1_5',
  'UNDER_1_5',
  'OVER_2_5',
  'UNDER_2_5',
] as const

export type BetBuilderMarketKey = (typeof BET_BUILDER_MARKET_KEYS)[number]

export type BetBuilderMarketChip = {
  key: 'all' | BetBuilderMarketKey
  label: string
}

export const BET_BUILDER_MARKET_CHIPS: BetBuilderMarketChip[] = [
  { key: 'all', label: 'Tutti' },
  { key: 'HOME', label: '1' },
  { key: 'DRAW', label: 'X' },
  { key: 'AWAY', label: '2' },
  { key: 'ONE_X', label: '1X' },
  { key: 'X_TWO', label: 'X2' },
  { key: 'ONE_TWO', label: '12' },
  { key: 'DRAW_PT', label: 'X PT' },
  { key: 'OVER_1_5', label: 'Over 1.5' },
  { key: 'UNDER_1_5', label: 'Under 1.5' },
  { key: 'OVER_2_5', label: 'Over 2.5' },
  { key: 'UNDER_2_5', label: 'Under 2.5' },
]

export async function fetchBetBuilderOpportunities(
  params: FetchBetBuilderOpportunitiesParams,
): Promise<BetBuilderOpportunitiesResponse> {
  const qs = new URLSearchParams()
  qs.set('date', params.date)
  if (params.market_key) qs.set('market_key', params.market_key)
  if (params.origin) qs.set('origin', params.origin)
  return requestJson<BetBuilderOpportunitiesResponse>(
    `/api/cecchino/bet-builder/opportunities?${qs.toString()}`,
  )
}
