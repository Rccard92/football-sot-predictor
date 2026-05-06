export type AuditMode = 'pre_match' | 'post_match'

export type AuditTeamBlock = { id: number; name: string; logo_url?: string | null }

export type AuditFixtureBlock = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: AuditTeamBlock
  away_team: AuditTeamBlock
}

export type AuditSampleRow = {
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

export type AuditVariable = {
  key: string
  label: string
  team_id: number | null
  team_name: string | null
  value: number | null
  unit: string | null
  status: 'available' | 'missing' | 'partial' | 'not_applicable'
  implementation_status: 'implemented' | 'partial' | 'debug_only' | 'todo'
  applied_to_model: boolean
  weight: number | null
  weight_label: string | null
  source_table: string | null
  source_description: string | null
  calculation: { formula: string; meta?: Record<string, unknown> | null; result?: number | null } | null
  sample_rows: AuditSampleRow[]
  notes: string | null
}

export type AuditSection = {
  id: string
  title: string
  variables: AuditVariable[]
  variables_available: number
  variables_missing: number
  completeness_pct: number
}

export type AuditResponse = {
  fixture: AuditFixtureBlock
  market: 'shots_on_target'
  mode: AuditMode
  data_policy: { no_data_leakage: boolean; included_matches_rule: string }
  sections: AuditSection[]
  model_inputs_summary: {
    home_team_expected_sot_v01: number | null
    away_team_expected_sot_v01: number | null
    home_team_expected_sot_v02: number | null
    away_team_expected_sot_v02: number | null
  }
}

export type FixturesListItem = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: AuditTeamBlock
  away_team: AuditTeamBlock
}

export type FixturesListResponse = {
  season: number | null
  scope: 'upcoming' | 'completed' | 'all'
  fixtures: FixturesListItem[]
}

