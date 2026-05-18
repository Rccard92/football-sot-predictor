export type AvailabilityPlayerRow = {
  api_player_id: number | null
  player_name: string
  availability_status: string
  availability_type: string | null
  reason: string | null
  source?: string
  shots_on_per90?: number | null
  team_sot_share?: number | null
  shooting_impact_score?: number | null
  is_top_shooter?: boolean
  high_impact?: boolean
  profile_found?: boolean
}

export type AvailabilityTeamSide = {
  team_id?: number
  team_name: string
  api_team_id?: number
  unavailable_count: number
  players: AvailabilityPlayerRow[]
}

export type FixtureAvailabilityResponse = {
  status: string
  fixture_id?: number
  api_fixture_id?: number
  season?: number
  availability_available?: boolean
  message?: string
  home?: AvailabilityTeamSide
  away?: AvailabilityTeamSide
  quality?: {
    source?: string
    api_live_call?: boolean
    model_impact?: boolean
    note?: string
  }
}

export type AvailabilityIngestSummary = {
  status: string
  season?: number
  fixtures_checked?: number
  teams_checked?: number
  api_calls?: number
  availability_records_upserted?: number
  players_matched_to_registry?: number
  players_not_matched_to_registry?: number
  top_shooters_flagged?: {
    player_name: string
    team_name?: string | null
    api_player_id?: number | null
    reason?: string | null
    availability_status?: string
    shooting_impact_score?: number | null
  }[]
  errors?: { error?: string; message?: string }[]
}

export type AvailabilitySeasonSummary = {
  status: string
  season: number
  league_id?: number
  total_records?: number
  active_records?: number
  inactive_records?: number
  active_with_fixture?: number
  active_with_registry?: number
  by_source?: Record<string, number>
}
