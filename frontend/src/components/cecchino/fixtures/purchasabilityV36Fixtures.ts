import type {
  V36Item,
  V36Snapshot,
} from '../../../lib/cecchinoTodayApi'
import { PANEL_MARKET_KEYS } from '../cecchinoPurchasabilityMarketKeys'

function baseScoredItem(overrides: Partial<V36Item> & { market_key: string }): V36Item {
  const { market_key, gate, input, components, ...rest } = overrides
  return {
    market_key,
    label: rest.label ?? market_key,
    status: 'score',
    gate_status: 'passed',
    gate: {
      gate_status: 'passed',
      gate_passed: true,
      expected_value: 0.12,
      probability_cecchino: 0.48,
      fair_book_probability: 0.4,
      rating: 72,
      ...(gate ?? {}),
    },
    input: {
      execution_quote: 2.2,
      execution_quote_real: true,
      probability_cecchino: 0.48,
      fair_book_probability: 0.4,
      rating: 72,
      overround: 1.05,
      book_fallback_used: false,
      fair_probability_may_be_derived: false,
      ...(input ?? {}),
    },
    components: {
      executable_value: { component: 'executable_value', score: 55, expected_value: 0.12 },
      market_disagreement: { component: 'market_disagreement', score: 48, delta_logit: 0.3 },
      base_rate_reliability: { component: 'base_rate_reliability', score: 62 },
      structural_coherence: {
        component: 'structural_coherence',
        score: 58,
        S: 58,
        S_raw: 57.2,
        structural_confidence: 0.8,
        structural_factor: 0.95,
        structural_status: 'available',
        blocks: [
          {
            block_type: 'same_family_opposition',
            block_raw: 60,
            block_confidence: 0.4,
            coverage: 1,
            configured_strength: 0.4,
            related_markets: ['DRAW', 'AWAY'],
            opponents: [
              { related_market: 'DRAW', support_score: 55, data_available: true },
              { related_market: 'AWAY', support_score: 65, data_available: true },
            ],
          },
          {
            block_type: 'side_cover',
            block_raw: 52,
            block_confidence: 0.3,
            coverage: 0.75,
            configured_strength: 0.4,
            related_markets: ['ONE_X'],
            opponents: [{ related_market: 'ONE_X', support_score: 52, data_available: true }],
          },
        ],
      },
      information_quality: {
        component: 'information_quality',
        score: 88,
        overround_penalty: 2,
        fallback_penalty: 0,
        derived_fair_penalty: 0,
        extreme_divergence_penalty: 0,
      },
      ...(components ?? {}),
    },
    value_core: 51.5,
    acquisition_core: 56.5,
    structural_factor: 0.95,
    quality_factor: 0.96,
    adjusted_confidence: 0.91,
    score: 47,
    raw_score: 47.2,
    class: 'Media',
    reference: {
      id: 'v35_structural_v2_reference',
      label: 'V3.5 Structural V2',
      score: 47,
      raw_score: 47.2,
      class: 'Media',
    },
    ...rest,
  }
}

export const HOME_V36_ITEM: V36Item = baseScoredItem({
  market_key: 'HOME',
  label: '1',
  score: 47,
  raw_score: 47.2,
  input: {
    execution_quote: 2.2,
    execution_quote_real: true,
    probability_cecchino: 0.48,
    fair_book_probability: 0.4,
    rating: 72,
  },
})

export const DRAW_V36_ITEM: V36Item = baseScoredItem({
  market_key: 'DRAW',
  label: 'X',
  score: 55,
  raw_score: 55.8,
  input: {
    execution_quote: 3.4,
    execution_quote_real: true,
    probability_cecchino: 0.28,
    fair_book_probability: 0.25,
    rating: 70,
  },
})

export const OVER_25_V36_ITEM: V36Item = baseScoredItem({
  market_key: 'OVER_2_5',
  label: 'Over 2.5',
  score: 41,
  raw_score: 41.1,
  input: {
    execution_quote: 1.85,
    execution_quote_real: true,
    probability_cecchino: 0.55,
    fair_book_probability: 0.52,
    rating: 68,
  },
})

export const S_MISSING_V36_ITEM: V36Item = baseScoredItem({
  market_key: 'AWAY',
  label: '2',
  score: 33,
  raw_score: 33.4,
  structural_missing_penalty_applied: true,
  structural_factor: 0.85,
  components: {
    executable_value: { component: 'executable_value', score: 40 },
    market_disagreement: { component: 'market_disagreement', score: 44 },
    base_rate_reliability: { component: 'base_rate_reliability', score: 50 },
    structural_coherence: {
      component: 'structural_coherence',
      score: null,
      S: null,
      S_raw: null,
      structural_confidence: null,
      structural_status: 'unavailable',
      structural_missing_penalty_applied: true,
      structural_factor: 0.85,
      blocks: [],
    },
    information_quality: {
      component: 'information_quality',
      score: 70,
      overround_penalty: 5,
      fallback_penalty: 3,
      derived_fair_penalty: 1,
      extreme_divergence_penalty: 0,
    },
  },
})

export const GATE_FAILED_V36_ITEM: V36Item = {
  market_key: 'UNDER_2_5',
  label: 'Under 2.5',
  status: 'gate_failed',
  gate_status: 'gate_failed',
  gate: {
    gate_status: 'gate_failed',
    gate_passed: false,
    reason: 'rating_below_min',
    reason_codes: ['rating_below_min'],
  },
  score: null,
  raw_score: null,
  components: {
    executable_value: null,
    market_disagreement: null,
    base_rate_reliability: null,
    structural_coherence: null,
    information_quality: null,
  },
}

function placeholder(marketKey: string, status: 'gate_failed' | 'not_calculable'): V36Item {
  return {
    market_key: marketKey,
    label: marketKey,
    status,
    gate_status: status,
    score: null,
    raw_score: null,
  }
}

function buildAllMarkets(): V36Item[] {
  const scored = new Map<string, V36Item>([
    ['HOME', HOME_V36_ITEM],
    ['DRAW', DRAW_V36_ITEM],
    ['OVER_2_5', OVER_25_V36_ITEM],
    ['AWAY', S_MISSING_V36_ITEM],
    ['UNDER_2_5', GATE_FAILED_V36_ITEM],
  ])
  return PANEL_MARKET_KEYS.map(
    (key) => scored.get(key) ?? placeholder(key, 'gate_failed'),
  )
}

export const V36_VALID_SNAPSHOT: V36Snapshot = {
  snapshot_version: 'cecchino_purchasability_v35_v2_snapshot_v1',
  contract_version: 'cecchino_purchasability_v35_v2_contract_v1',
  formula_version: 'cecchino_purchasability_v35_structural_v2',
  formula_freeze_sha256:
    '3488f0d8e97f52b3db126ff96758c51adef0acfc8fd98f953b2443e629cd0bfe',
  experiment_version: 'cecchino_purchasability_v35_live_experiment_v2',
  registry_status: 'shadow_live_experiment',
  pre_match_only: true,
  items: buildAllMarkets(),
}

export const V36_NO_SCORE_SNAPSHOT: V36Snapshot = {
  ...V36_VALID_SNAPSHOT,
  items: PANEL_MARKET_KEYS.map((key) => placeholder(key, 'gate_failed')),
}
