/**
 * Client API Bet Builder BET-01 — contratti tipizzati + fetch opportunities.
 * UI completa in BET-02; qui solo il contratto client.
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

export type BetBuilderContextSupport = {
  available: boolean
  module?: string | null
  status?: string
  reason?: string
  payload?: Record<string, unknown> | null
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

export type BetBuilderOpportunitiesResponse = {
  contract_version: string
  aggregator_version: string
  signal_evidence_version?: string
  purchasability_policy_version?: string
  purchasability_policy: string
  scan_date: string
  source_revision: string
  source_generated_from?: Record<string, unknown>
  source_scan_status?: string | null
  freshness: Record<string, unknown>
  summary: BetBuilderOpportunitiesSummary
  opportunities: BetBuilderOpportunity[]
}

export type FetchBetBuilderOpportunitiesParams = {
  date: string
  market_key?: string
  origin?: BetBuilderOrigin
}

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
