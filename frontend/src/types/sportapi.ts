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

export type SportApiLineupsStoredResponse = {
  status: string
  fixture_id: number
  mapping?: {
    provider_event_id: number
    confidence_score?: number | null
    matched_by?: string | null
  } | null
  confirmed?: boolean | null
  home_formation?: string | null
  away_formation?: string | null
  fetched_at?: string | null
  home?: {
    players: SportApiPlayerRow[]
    substitutes: SportApiPlayerRow[]
    missing_players: SportApiMissingRow[]
  }
  away?: {
    players: SportApiPlayerRow[]
    substitutes: SportApiPlayerRow[]
    missing_players: SportApiMissingRow[]
  }
  model_usage?: { used_in_prediction: boolean; note: string }
  raw_payload?: unknown
}

export type SportApiPlayerRow = {
  provider_player_id: number
  player_name: string
  short_name?: string | null
  position?: string | null
  jersey_number?: number | null
  is_substitute?: boolean
  avg_rating?: number | null
}

export type SportApiMissingRow = {
  provider_player_id: number
  player_name: string
  position?: string | null
  jersey_number?: number | null
  reason?: string | null
  description?: string | null
  external_type?: string | null
  expected_end_date?: string | null
}
