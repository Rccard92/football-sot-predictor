import type {
  CecchinoPurchasabilityV35Item,
  CecchinoPurchasabilityV35Snapshot,
} from '../../../lib/cecchinoTodayApi'
import { PANEL_MARKET_KEYS } from '../cecchinoPurchasabilityV35UiUtils'

const CANDIDATE_REGISTRY = {
  A: {
    id: 'v35_a_balanced_structural_v1',
    name: 'V3.5-A Balanced Structural',
    weights: { V: 0.4, D: 0.25, S: 0.2, Q: 0.15 },
  },
  B: {
    id: 'v35_b_value_heavy_v1',
    name: 'V3.5-B Value Heavy',
    weights: { V: 0.55, D: 0.2, S: 0.15, Q: 0.1 },
  },
  C: {
    id: 'v35_c_structure_heavy_v1',
    name: 'V3.5-C Structure Heavy',
    weights: { V: 0.35, D: 0.2, S: 0.3, Q: 0.15 },
  },
  D: {
    id: 'v35_d_quality_conservative_v1',
    name: 'V3.5-D Quality Conservative',
    weights: { V: 0.35, D: 0.2, S: 0.15, Q: 0.3 },
  },
} as const

function buildCandidates(scores: { A: number; B: number; C: number; D: number }) {
  const classes: Record<number, string> = {
    63: 'Alta',
    58: 'Media',
    35: 'Bassa',
    8: 'Molto Bassa',
    5: 'Molto Bassa',
    57: 'Media',
    55: 'Media',
    53: 'Media',
    60: 'Alta',
  }
  return Object.fromEntries(
    (['A', 'B', 'C', 'D'] as const).map((key) => [
      key,
      {
        candidate_id: CANDIDATE_REGISTRY[key].id,
        candidate_name: CANDIDATE_REGISTRY[key].name,
        raw_score: scores[key] - 0.33,
        score: scores[key],
        class: classes[scores[key]] ?? 'Media',
        configured_weights: CANDIDATE_REGISTRY[key].weights,
        effective_weights: CANDIDATE_REGISTRY[key].weights,
        missing_components: [],
      },
    ]),
  )
}

export const HOME_V35_ITEM: CecchinoPurchasabilityV35Item = {
  market_key: 'HOME',
  label: '1',
  status: 'score',
  gate_status: 'passed',
  gate: {
    gate_status: 'passed',
    gate_passed: true,
    expected_value: 0.21,
    probability_cecchino: 0.55,
    fair_book_probability: 0.45,
    rating: 60,
  },
  input: {
    execution_quote_real: 2.2,
    execution_quote_source: 'betfair_raw_match_winner',
    probability_cecchino: 0.55,
    fair_book_probability: 0.45,
    rating: 60,
    overround: 0.05,
    book_fallback_used: false,
    fair_probability_may_be_derived: false,
  },
  components: {
    executable_value: { score: 50.3, expected_value: 0.21, status: 'available' },
    market_disagreement: { score: 80.3, delta_logit: 0.41, status: 'available' },
    structural_coherence: {
      score: 26.0,
      raw_score: 10.1,
      structural_confidence: 0.6,
      coverage: 1.0,
      configured_relation_count: 1,
      available_relation_count: 1,
      structural_status: 'available',
      status: 'available',
      relations: [
        {
          related_market: 'ONE_X',
          support_score: 10.1,
          related_delta_logit: -0.49,
          relation_weight: 0.6,
        },
      ],
    },
    information_quality: {
      score: 75.0,
      overround_penalty: 5,
      fallback_penalty: 0,
      derived_fair_penalty: 0,
      extreme_divergence_penalty: 0,
      status: 'available',
    },
  },
  candidates: buildCandidates({ A: 63, B: 59, C: 65, D: 69 }),
  diagnostics: {
    expected_value: 0.21,
    delta_logit: 0.41,
    hours_to_kickoff: 5,
  },
}

export const OVER_25_V35_ITEM: CecchinoPurchasabilityV35Item = {
  market_key: 'OVER_2_5',
  label: 'Over 2.5',
  status: 'score',
  gate_status: 'passed',
  gate: { gate_status: 'passed', gate_passed: true, rating: 62 },
  input: {
    execution_quote_real: 1.95,
    probability_cecchino: 0.52,
    fair_book_probability: 0.48,
    rating: 62,
    overround: 0.04,
    book_fallback_used: false,
    fair_probability_may_be_derived: false,
  },
  components: {
    executable_value: { score: 45.0, status: 'available' },
    market_disagreement: { score: 55.0, status: 'available' },
    structural_coherence: { score: null, structural_status: 'unavailable', status: 'unavailable' },
    information_quality: { score: 88.0, status: 'available' },
  },
  candidates: buildCandidates({ A: 58, B: 52, C: 61, D: 65 }),
  diagnostics: { hours_to_kickoff: 5 },
}

export const LOW_SCORE_V35_ITEM: CecchinoPurchasabilityV35Item = {
  market_key: 'DRAW',
  label: 'X',
  status: 'score',
  gate_status: 'passed',
  gate: { gate_status: 'passed', gate_passed: true, rating: 51 },
  input: { rating: 51, probability_cecchino: 0.3, fair_book_probability: 0.28 },
  components: {
    executable_value: { score: 8.0, status: 'available' },
    market_disagreement: { score: 12.0, status: 'available' },
    structural_coherence: { score: null, structural_status: 'unavailable', status: 'unavailable' },
    information_quality: { score: 70.0, status: 'available' },
  },
  candidates: buildCandidates({ A: 8, B: 5, C: 12, D: 6 }),
}

export const GATE_FAILED_V35_ITEM: CecchinoPurchasabilityV35Item = {
  market_key: 'AWAY',
  label: '2',
  status: 'gate_failed',
  gate_status: 'gate_failed',
  gate: {
    gate_status: 'gate_failed',
    gate_passed: false,
    reason_codes: ['rating_below_gate'],
    rating: 40,
  },
  input: { rating: 40 },
  components: {
    executable_value: null,
    market_disagreement: null,
    structural_coherence: null,
    information_quality: null,
  },
  candidates: buildCandidates({ A: 0, B: 0, C: 0, D: 0 }),
}

function buildPlaceholderItem(marketKey: string, status: 'gate_failed' | 'not_calculable'): CecchinoPurchasabilityV35Item {
  return {
    market_key: marketKey,
    label: marketKey,
    status,
    gate_status: status === 'gate_failed' ? 'gate_failed' : 'unavailable_inputs',
    components: {
      executable_value: null,
      market_disagreement: null,
      structural_coherence: null,
      information_quality: null,
    },
    candidates: {},
  }
}

function buildAllMarkets(): CecchinoPurchasabilityV35Item[] {
  const scored = new Map<string, CecchinoPurchasabilityV35Item>([
    ['HOME', HOME_V35_ITEM],
    ['OVER_2_5', OVER_25_V35_ITEM],
    ['DRAW', LOW_SCORE_V35_ITEM],
    ['AWAY', GATE_FAILED_V35_ITEM],
  ])
  return PANEL_MARKET_KEYS.map((key) => scored.get(key) ?? buildPlaceholderItem(key, 'gate_failed'))
}

export const V35_VALID_SNAPSHOT: CecchinoPurchasabilityV35Snapshot = {
  snapshot_version: 'cecchino_purchasability_v35_snapshot_v1',
  contract_version: 'cecchino_purchasability_v35_contract_v1',
  feature_version: 'cecchino_purchasability_v35_features_v1',
  formula_version: 'cecchino_purchasability_v35_structural_v1',
  relation_registry_version: 'cecchino_purchasability_v35_relations_v1',
  candidate_registry_version: 'cecchino_purchasability_v35_candidates_v1',
  registry_status: 'shadow_live_experiment',
  experiment_version: 'cecchino_purchasability_v35_live_experiment_v1',
  generated_at: '2026-08-19T10:00:00+00:00',
  source_snapshot_at: '2026-08-19T10:00:00+00:00',
  pre_match_verified: true,
  input_fingerprint_sha256: 'abc123',
  engine_payload_sha256: 'def456',
  candidate_registry: { ...CANDIDATE_REGISTRY },
  frozen_config: { candidates: { ...CANDIDATE_REGISTRY }, rating_min_gate: 50 },
  items: buildAllMarkets(),
  summary: {
    A: { top_market_key: 'HOME', top_score: 63 },
    B: { top_market_key: 'HOME', top_score: 59 },
    C: { top_market_key: 'HOME', top_score: 65 },
    D: { top_market_key: 'HOME', top_score: 69 },
  },
  pre_match_only: true,
  historical_reliability_integrated: false,
  shadow_candidate: true,
  warnings: [],
}

export const V35_NO_SCORE_SNAPSHOT: CecchinoPurchasabilityV35Snapshot = {
  ...V35_VALID_SNAPSHOT,
  items: PANEL_MARKET_KEYS.map((key) => buildPlaceholderItem(key, 'gate_failed')),
  summary: {},
}
