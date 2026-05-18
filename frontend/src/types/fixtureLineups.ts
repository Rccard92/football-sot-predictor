export type LineupPlayerRow = {
  api_player_id: number | null
  player_name: string
  number: number | null
  position: string | null
  grid: string | null
  is_starter: boolean
  is_substitute: boolean
  is_top_shooter_starter?: boolean
  shots_on_per90?: number | null
  shots_total_per90?: number | null
  shooting_impact_score?: number | null
  reliability_score?: number | null
}

export type LineupTeamSide = {
  team_name: string
  formation: string | null
  coach_name?: string | null
  starters: LineupPlayerRow[]
  substitutes: LineupPlayerRow[]
}

export type FixtureLineupsResponse = {
  status: string
  fixture_id?: number
  lineups_available?: boolean
  message?: string
  home?: LineupTeamSide
  away?: LineupTeamSide
  quality?: {
    source?: string
    api_live_call?: boolean
    model_impact?: boolean
    note?: string
  }
}

export type LineupsIngestSummary = {
  status: string
  season?: number
  fixtures_checked?: number
  fixtures_with_lineups?: number
  fixtures_without_lineups?: number
  lineups_upserted?: number
  lineup_players_upserted?: number
  not_available_yet?: { fixture_id: number; api_fixture_id: number; message: string }[]
  errors?: { fixture_id?: number; message?: string; error?: string }[]
}
