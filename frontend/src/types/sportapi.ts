export type SportApiScoreBreakdown = Record<string, number>

export type SportApiCandidate = {
  provider_event_id: number
  start_timestamp?: number | null
  home_team_name?: string
  away_team_name?: string
  tournament?: Record<string, unknown>
  confidence_score: number
  score_breakdown: SportApiScoreBreakdown
  recommendation: string
}

export type SportApiFixtureDebugResponse = {
  status: string
  message?: string
  sportapi_enabled?: boolean
  use_sportapi_lineups_in_model?: boolean
  input_id?: number
  resolved_via?: 'db_id' | 'api_fixture_id' | null
  fixture?: {
    fixture_id: number
    api_fixture_id: number
    league_id?: number
    league_api_id?: number | null
    league_name?: string | null
    season_id?: number
    round?: string | null
    timezone?: string | null
    home_team_id?: number
    home_team_name?: string | null
    away_team_id?: number
    away_team_name?: string | null
    kickoff_at?: string
    kickoff_timestamp?: number
    match_date?: string
    resolved_via?: 'db_id' | 'api_fixture_id' | null
  }
  candidates?: SportApiCandidate[]
  best_candidate?: SportApiCandidate | null
  confidence_score?: number | null
  matched_by?: string | null
  recommendation?: string
  score_explanation?: string
  scheduled_events_count?: number
  api_calls?: number
}

export type SportApiDisplayRole = 'P' | 'D' | 'C' | 'A'

export type SportApiLineupPlayer = {
  provider_player_id: number
  player_name: string
  short_name?: string | null
  position?: string | null
  display_role: SportApiDisplayRole
  jersey_number?: number | null
  is_substitute?: boolean
  avg_rating?: number | null
  original_index?: number
}

export type SportApiMissingPlayer = {
  provider_player_id: number
  player_name: string
  short_name?: string | null
  position?: string | null
  display_role: SportApiDisplayRole
  jersey_number?: number | null
  reason?: string | null
  description?: string | null
  external_type?: string | null
  expected_end_date?: string | null
  original_index?: number
}

export type SportApiMissingGrouped = {
  injured: SportApiMissingPlayer[]
  suspended: SportApiMissingPlayer[]
  other: SportApiMissingPlayer[]
}

export type SportApiTeamLineupSide = {
  team_name: string
  formation?: string | null
  confirmed?: boolean | null
  starters: SportApiLineupPlayer[]
  substitutes: SportApiLineupPlayer[]
  tactical_lines?: SportApiLineupPlayer[][]
  missing_players: SportApiMissingGrouped
}

export type SportApiLineupsAuditPayload = {
  available: boolean
  provider_event_id?: number | null
  confidence_score?: number | null
  confirmed?: boolean | null
  fetched_at?: string | null
  home: SportApiTeamLineupSide
  away: SportApiTeamLineupSide
}

/** Risposta GET admin/sportapi/lineups (include metadati + payload audit). */
export type SportApiLineupsStoredResponse = SportApiLineupsAuditPayload & {
  status: string
  fixture_id: number
  input_id?: number
  mapping?: {
    provider_event_id: number
    confidence_score?: number | null
    matched_by?: string | null
  } | null
  home_formation?: string | null
  away_formation?: string | null
  model_usage?: { used_in_prediction: boolean; note: string }
  raw_payload?: unknown
}

/** @deprecated usa SportApiLineupPlayer */
export type SportApiPlayerRow = SportApiLineupPlayer

/** @deprecated usa SportApiMissingPlayer */
export type SportApiMissingRow = SportApiMissingPlayer
