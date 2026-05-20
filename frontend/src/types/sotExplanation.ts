import type { SportApiLineupsAuditPayload } from './sportapi'
import type { LineupImpactSimulationPayload } from './lineupImpact'

export type ExplanationStatus = 'ok' | 'missing' | 'error'

export type ExplanationFixtureTeam = { id: number; name: string; logo_url?: string | null }

export type ExplanationFixture = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: ExplanationFixtureTeam
  away_team: ExplanationFixtureTeam
}

export type SideSummary = {
  team_name: string
  predicted_sot: number | null
  actual_sot: number | null
  absolute_error: number | null
  outcome_label: string | null
  post_audit_judgment: string | null
}

export type ExplanationSampleRow = {
  fixture_id: number
  date: string
  home_team: string
  away_team: string
  team: string
  team_id: number
  opponent: string
  opponent_id: number
  side: 'home' | 'away'
  shots_on_target: number | null
  total_shots: number | null
  goals_for: number | null
  goals_against: number | null
}

export type ExplanationVariable = {
  key: string
  label: string
  value: number | null
  unit: string | null
  weight_internal: number | null
  contribution: number | null
  formula: string | null
  data_source: string | null
  matches_count?: number | null
  sum?: number | null
  sample_rows_count?: number | null
  fallback_used: boolean
  cap_applied: boolean
  no_data_leakage_note?: string | null
  sample_matches?: ExplanationSampleRow[]
  sample_matches_note?: string | null
  status?: string
  parent_component_id?: string
  raw_value?: number | null
  normalized_value?: number | null
  internal_weight?: number | null
  internal_contribution?: number | null
}

export type FormulaFlags = {
  cap_applied: boolean
  fallbacks_used: string[]
}

export type InternalFormulaBlock = {
  title: string
  formula_text?: string
  formula_symbolic?: string
  formula_numeric?: string
  component_value?: number | null
  rows: Record<string, unknown>[]
  notes: string[]
  flags: FormulaFlags
}

export type ExplanationComponent = {
  id: string
  label: string
  value: number | null
  weight: number | null
  contribution: number | null
  direction: string
  data_status: string
  notes?: string | null
  variables: ExplanationVariable[]
  internal_formula?: InternalFormulaBlock
}

export type FormulaTerm = {
  id: string
  label: string
  symbol: string
  value: number | null
  weight: number | null
  contribution: number | null
  calc_expression: string
}

export type FormulaComponentTableRow = {
  componente: string
  valore_componente: number | null
  peso: number | null
  calcolo_contributo: string
  contributo_finale: number | null
  source_path?: string | null
  fallback_used?: boolean
  fallback_reason?: string | null
  status?: string | null
}

export type PredictionFormulaBreakdownSide = {
  model_version: string
  stored_predicted_sot: number | null
  terms: FormulaTerm[]
  formula_terms_count?: number
  formula_quality_status?: string | null
  formula_quality_warnings?: string[]
  formula_symbolic: string
  formula_numeric: string
  components_table: FormulaComponentTableRow[]
  sum_contributions: number | null
  delta_vs_stored: number | null
  checksum_warning: string | null
  flags: FormulaFlags
}

export type FrameworkConsistencySide = {
  framework_applied_count: number
  debug_trace_count: number
  is_consistent: boolean
  missing_trace_keys: string[]
  extra_trace_keys: string[]
  missing_data_keys: string[]
  validation_warnings: string[]
}

export type FrameworkConsistencyPayload = {
  model_version?: string | null
  home: FrameworkConsistencySide
  away: FrameworkConsistencySide
}

export type AppliedVariableTraceRow = {
  key: string
  trace_key: string
  label: string
  area: string
  application_role: string
  parent_component: string | null
  team_id: number
  team_name: string
  value: unknown
  unit: string | null
  weight: number | null
  contribution: number | null
  formula: string | null
  source: string | null
  matches_count?: number | null
  sample_rows_count?: number | null
  fallback_used: boolean
  cap_applied: boolean
  notes: string | null
  status?: string
  model_version?: string
}

export type ComponentTreeNode = {
  component_key: string | null
  component_label: string | null
  value: number | null
  weight: number | null
  contribution: number | null
  data_status?: string
  notes?: string | null
  variables: ExplanationVariable[]
}

export type FinalFormulaTerm = {
  component_key: string | null
  component_label: string | null
  value: number | null
  weight: number | null
  contribution: number | null
}

export type FinalFormulaSide = {
  terms: FinalFormulaTerm[]
  sum_contributions: number | null
  saved_expected_sot: number | null
  delta: number | null
  checksum_warning?: string | null
}

export type ModelComparisonRow = {
  model_version: string
  label: string
  home: number | null
  away: number | null
  total: number | null
}

export type SotFixtureExplanationResponse = {
  status: ExplanationStatus
  message?: string
  fixture_id?: number
  fixture?: ExplanationFixture
  market?: string
  active_model_version?: string | null
  framework_consistency?: FrameworkConsistencyPayload
  prediction_summary?: {
    audit_mode: string
    ui_mode: string
    home: SideSummary
    away: SideSummary
    match_total: {
      predicted_sot: number | null
      actual_sot: number | null
      absolute_error: number | null
    }
  }
  actual_result?: {
    fixture_finished: boolean
    home_actual_sot: number | null
    away_actual_sot: number | null
  }
  model_comparison?: {
    rows: ModelComparisonRow[]
    deltas_text: string[]
  }
  components?: { home: ExplanationComponent[]; away: ExplanationComponent[] }
  prediction_formula_breakdown?: {
    home: PredictionFormulaBreakdownSide | null
    away: PredictionFormulaBreakdownSide | null
  }
  final_formula?: {
    formula_label?: string
    home: FinalFormulaSide | null
    away: FinalFormulaSide | null
  }
  component_tree?: { home: ComponentTreeNode[]; away: ComponentTreeNode[] }
  applied_variable_trace?: { home: AppliedVariableTraceRow[]; away: AppliedVariableTraceRow[] }
  not_applied_variables?: { items: unknown[]; note?: string | null }
  variables_used?: { home: ExplanationVariable[]; away: ExplanationVariable[] }
  quality_checks?: { status: string; items: string[] }
  human_summary?: string
  technical_audit?: {
    prediction_raw_json: { home: unknown; away: unknown }
    data_policy: { no_data_leakage: boolean; included_matches_rule: string } | null
  }
  sportapi_lineups?: SportApiLineupsAuditPayload
  lineup_impact_simulation?: LineupImpactSimulationPayload
}
