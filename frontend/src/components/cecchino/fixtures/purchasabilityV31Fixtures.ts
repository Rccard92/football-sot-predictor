import type {
  CecchinoKpiExplanation,
  CecchinoPurchasabilityV31Item,
  CecchinoPurchasabilityV31Snapshot,
} from '../../../lib/cecchinoTodayApi'

/** Fixture V3.1: mercato AWAY con score calcolato. */
export const AWAY_V31_ITEM: CecchinoPurchasabilityV31Item = {
  market_key: 'AWAY',
  market_label: '2',
  market_family: 'MATCH_WINNER_FT',
  status: 'score',
  score: 52,
  raw_score: 51.8,
  class: 'Media',
  gate_status: 'passed',
  gate_passed: true,
  theoretical_raw: 86.3,
  historical_factor: 0.6,
  historical_multiplier: 0.6,
  total_penalty: 12,
  formula_version: 'cecchino_purchasability_v31_shadow_v1',
  candidate_version: 'cecchino_purchasability_v31_candidate_1',
  input: {
    quota_book: 9.5,
    quota_cecchino: 5.19,
    edge_pct: 83.04,
  },
  explanation: {
    final_state: {
      status: 'score',
      score: 52,
      class: 'Media',
    },
    gate: {
      gate_status: 'passed',
      gate_passed: true,
    },
    theoretical_value: {
      theoretical_raw: 86.3,
      edge_pct: 83.04,
    },
    historical_reliability: {
      factor: 0.6,
      historical_multiplier: 0.6,
      score: 72,
      class: 'Buona',
      sample_size: 45,
    },
    penalties: {
      total_penalty: 12,
      penalties_applied: [
        { key: 'probability_risk', label: 'Rischio di probabilità', points: 8 },
        { key: 'family_ambiguity', label: 'Ambiguità famiglia', points: 4 },
      ],
    },
    final_calculation: {
      theoretical_raw: 86.3,
      historical_factor: 0.6,
      historical_multiplier: 0.6,
      raw_result: 51.78,
      score: 52,
      rounding: 'ROUND_HALF_UP',
    },
    comparison_with_v3: {
      v3_score: 47,
      v31_score: 52,
      delta: 5,
      direction: 'V3.1 superiore',
    },
  },
  warnings: [],
}

/** Fixture V3.1: gate fallito per rating sotto 50. */
export const GATE_FAILED_RATING_V31_ITEM: CecchinoPurchasabilityV31Item = {
  market_key: 'HOME',
  market_label: '1',
  market_family: 'MATCH_WINNER_FT',
  status: 'gate_failed',
  score: null,
  reason: 'Rating sotto 50',
  reason_code: 'rating_below_50',
  gate_status: 'failed',
  gate_passed: false,
  formula_version: 'cecchino_purchasability_v31_shadow_v1',
  candidate_version: 'cecchino_purchasability_v31_candidate_1',
  input: {
    rating: 40,
    edge_pct: -15,
  },
  explanation: {
    final_state: {
      status: 'gate_failed',
      reason: 'Rating sotto 50',
      reason_code: 'rating_below_50',
    },
    gate: {
      gate_status: 'failed',
      gate_passed: false,
      reason: 'Rating sotto 50',
      reason_code: 'rating_below_50',
    },
  },
}

/** Fixture V3.1: gate fallito per nessun valore positivo. */
export const GATE_FAILED_NO_VALUE_V31_ITEM: CecchinoPurchasabilityV31Item = {
  market_key: 'DRAW',
  market_label: 'X',
  market_family: 'MATCH_WINNER_FT',
  status: 'gate_failed',
  score: null,
  reason: 'Nessun valore positivo',
  reason_code: 'no_positive_value',
  gate_status: 'failed',
  gate_passed: false,
  formula_version: 'cecchino_purchasability_v31_shadow_v1',
  candidate_version: 'cecchino_purchasability_v31_candidate_1',
  input: {
    edge_pct: -5,
  },
  explanation: {
    final_state: {
      status: 'gate_failed',
      reason: 'Nessun valore positivo',
      reason_code: 'no_positive_value',
    },
    gate: {
      gate_status: 'failed',
      gate_passed: false,
      reason: 'Nessun valore positivo',
      reason_code: 'no_positive_value',
    },
  },
}

/** Fixture V3.1: non calcolabile per quota mancante. */
export const NON_CALCULABLE_MISSING_QUOTE_V31_ITEM: CecchinoPurchasabilityV31Item = {
  market_key: 'OVER_1_5',
  market_label: 'Over 1.5',
  market_family: 'GOALS_FT',
  status: 'non_calculable',
  score: null,
  reason: 'Quota mancante',
  reason_code: 'missing_quote',
  formula_version: 'cecchino_purchasability_v31_shadow_v1',
  candidate_version: 'cecchino_purchasability_v31_candidate_1',
  explanation: {
    final_state: {
      status: 'non_calculable',
      reason: 'Quota mancante',
      reason_code: 'missing_quote',
    },
  },
}

/** Fixture V3.1: non calcolabile per quota derivata. */
export const NON_CALCULABLE_DERIVED_V31_ITEM: CecchinoPurchasabilityV31Item = {
  market_key: 'X_TWO',
  market_label: 'X2',
  market_family: 'DOUBLE_CHANCE',
  status: 'non_calculable',
  score: null,
  reason: 'Quota derivata',
  reason_code: 'derived_quote',
  formula_version: 'cecchino_purchasability_v31_shadow_v1',
  candidate_version: 'cecchino_purchasability_v31_candidate_1',
  input: {
    performance_type: 'derived',
  },
  explanation: {
    final_state: {
      status: 'non_calculable',
      reason: 'Quota derivata',
      reason_code: 'derived_quote',
    },
  },
}

/** Fixture V3.1: score provvisorio per storico insufficiente (non più non_calculable). */
export const SCORE_PROVISIONAL_INSUFFICIENT_HISTORY_V31_ITEM: CecchinoPurchasabilityV31Item = {
  market_key: 'UNDER_2_5',
  market_label: 'Under 2.5',
  market_family: 'GOALS_FT',
  status: 'score_provisional',
  score: 53,
  class: 'Media',
  calculation_quality: 'provisional',
  formula_version: 'cecchino_purchasability_v31_fixed_discount_empirical_v2',
  candidate_version: 'cecchino_purchasability_v31_candidate_2',
  historical: {
    sample_size: 16,
    selected_sample_size: 16,
    min_sample: 30,
    historical_multiplier: 1,
    historical_evidence_quality: 'provisional',
    historical_reliability_score: 50,
  },
  historical_multiplier: 1,
  theoretical_raw_score: 53.4134,
  explanation: {
    final_state: {
      status: 'score_provisional',
      score: 53,
      class: 'Media',
    },
  },
}

/** Legacy alias — non più usato come non_calculable. */
export const NON_CALCULABLE_INSUFFICIENT_HISTORY_V31_ITEM =
  SCORE_PROVISIONAL_INSUFFICIENT_HISTORY_V31_ITEM

/** Snapshot V3.1 completo. */
export const V31_SNAPSHOT: CecchinoPurchasabilityV31Snapshot = {
  snapshot_version: 'cecchino_purchasability_snapshot_v31',
  candidate_version: 'cecchino_purchasability_v31_candidate_1',
  candidate_name: 'v31_shadow',
  formula_version: 'cecchino_purchasability_v31_shadow_v1',
  audit_version: 'cecchino_purchasability_v31_audit_v1',
  status: 'ok',
  items: [
    AWAY_V31_ITEM,
    GATE_FAILED_RATING_V31_ITEM,
    GATE_FAILED_NO_VALUE_V31_ITEM,
  ],
  generated_at: '2026-08-05T12:00:00+00:00',
  source_snapshot_at: '2026-08-05T10:00:00+00:00',
  pre_match_only: true,
}

/** Builder per explanation V3.1 AWAY. */
export function buildAwayV31Explanation(
  overrides?: Partial<CecchinoKpiExplanation>,
): CecchinoKpiExplanation {
  const item = AWAY_V31_ITEM
  return {
    module: 'purchasability',
    market_key: 'AWAY',
    market_label: '2',
    metric_key: 'purchasability_v31',
    metric_label: 'Acquistabilità V3.1',
    status: 'available',
    calculation_type: 'purchasability_v31_shadow',
    description:
      'Misura quanto del valore Cecchino rimane dopo penalità, pesato per affidabilità storica.',
    purpose: 'Indice shadow V3.1 — formula candidata in osservazione.',
    formula_symbolic:
      'raw = theoretical_raw × historical_factor; score = ROUND_HALF_UP(raw)',
    formula_applied: [
      'theoretical_raw = 86.3',
      'historical_factor = 0.6',
      'raw = 86.3 × 0.6 = 51.78',
      'score = ROUND_HALF_UP(51.78) = 52',
    ],
    inputs: [],
    stored_result: 52,
    stored_result_display: '52',
    audit_result: 51.78,
    consistency: { status: 'rounding_match', delta: 0.22 },
    rounding: { policy: 'ROUND_HALF_UP', precision: 0, display_precision: 0 },
    formula_version: 'cecchino_purchasability_v31_shadow_v1',
    candidate_version: 'cecchino_purchasability_v31_candidate_1',
    audit_version: 'cecchino_purchasability_v31_audit_v1',
    generated_at: '2026-08-05T12:00:00+00:00',
    source_snapshot_at: '2026-08-05T10:00:00+00:00',
    market_family: 'MATCH_WINNER_FT',
    market_family_label: 'Esito finale 1/X/2',
    final_state: item.explanation?.final_state,
    gate: item.explanation?.gate,
    theoretical_value: item.explanation?.theoretical_value,
    historical_reliability: item.explanation?.historical_reliability,
    penalties: item.explanation?.penalties,
    final_calculation: item.explanation?.final_calculation,
    comparison_with_v3: item.explanation?.comparison_with_v3,
    input: item.input,
    persisted_result: {
      score: 52,
      class: 'Media',
      status: 'score',
    },
    data_origin: {
      generated_at: '2026-08-05T12:00:00+00:00',
      source_snapshot_at: '2026-08-05T10:00:00+00:00',
    },
    ...overrides,
  } as CecchinoKpiExplanation
}

/** Builder per explanation V3.1 gate failed. */
export function buildGateFailedV31Explanation(
  overrides?: Partial<CecchinoKpiExplanation>,
): CecchinoKpiExplanation {
  const item = GATE_FAILED_RATING_V31_ITEM
  return {
    module: 'purchasability',
    market_key: 'HOME',
    market_label: '1',
    metric_key: 'purchasability_v31',
    metric_label: 'Acquistabilità V3.1',
    status: 'partial',
    description: 'Indice non attivato per rating sotto la soglia.',
    purpose: 'Indice shadow V3.1 — formula candidata in osservazione.',
    formula_symbolic: 'Gate non superato',
    formula_applied: [],
    inputs: [],
    stored_result: null,
    stored_result_display: 'Non attivato',
    audit_result: null,
    consistency: { status: 'match' },
    formula_version: 'cecchino_purchasability_v31_shadow_v1',
    candidate_version: 'cecchino_purchasability_v31_candidate_1',
    audit_version: 'cecchino_purchasability_v31_audit_v1',
    final_state: item.explanation?.final_state,
    gate: item.explanation?.gate,
    input: item.input,
    persisted_result: {
      score: null,
      status: 'gate_failed',
      reason_code: 'rating_below_50',
    },
    ...overrides,
  } as CecchinoKpiExplanation
}

/** Builder per explanation V3.1 non calcolabile. */
export function buildNonCalculableV31Explanation(
  overrides?: Partial<CecchinoKpiExplanation>,
): CecchinoKpiExplanation {
  const item = NON_CALCULABLE_MISSING_QUOTE_V31_ITEM
  return {
    module: 'purchasability',
    market_key: 'OVER_1_5',
    market_label: 'Over 1.5',
    metric_key: 'purchasability_v31',
    metric_label: 'Acquistabilità V3.1',
    status: 'unavailable',
    description: 'Input mancanti per il calcolo.',
    purpose: 'Indice shadow V3.1 — formula candidata in osservazione.',
    formula_symbolic: 'Non calcolabile',
    formula_applied: [],
    inputs: [],
    stored_result: null,
    stored_result_display: 'Non calcolabile',
    audit_result: null,
    consistency: { status: 'not_verifiable' },
    formula_version: 'cecchino_purchasability_v31_shadow_v1',
    candidate_version: 'cecchino_purchasability_v31_candidate_1',
    final_state: item.explanation?.final_state,
    persisted_result: {
      score: null,
      status: 'non_calculable',
      reason_code: 'missing_quote',
    },
    ...overrides,
  } as CecchinoKpiExplanation
}
