export type PlayerDbProfileRow = {
  player_id: string
  api_player_id: number
  name: string
  position: string | null
  matches_played: number | null
  minutes_total: number | null
  recent_minutes_last5: number | null
  shots_total: number | null
  shots_on: number | null
  shots_total_per90: number | null
  shots_on_per90: number | null
  shot_accuracy: number | null
  team_shots_share: number | null
  team_sot_share: number | null
  avg_rating: number | null
  shooting_impact_score: number | null
  reliability_score: number | null
}

export type PlayerDbTeamSide = {
  team_id: number | null
  api_team_id: number
  team_name: string
  profiles_total: number
  profiles_returned: number
  players: PlayerDbProfileRow[]
}

export type FixturePlayerProfilesQuality = {
  source: string
  api_live_call: boolean
  model_impact: boolean
  note: string
}

export type FixturePlayerProfilesResponse = {
  status: 'success' | 'error'
  fixture_id?: number
  season?: number
  message?: string
  home?: PlayerDbTeamSide
  away?: PlayerDbTeamSide
  quality?: FixturePlayerProfilesQuality
}
