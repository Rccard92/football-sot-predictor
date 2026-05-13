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
  variables_used?: { home: ExplanationVariable[]; away: ExplanationVariable[] }
  quality_checks?: { status: string; items: string[] }
  human_summary?: string
  technical_audit?: {
    prediction_raw_json: { home: unknown; away: unknown }
    data_policy: { no_data_leakage: boolean; included_matches_rule: string } | null
  }
}
