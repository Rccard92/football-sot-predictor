export type MatchRecommendation = 'AUTO_SAFE' | 'REVIEW' | 'NO_MATCH'

export type PlayerLineupStatus =
  | 'STARTER'
  | 'BENCH'
  | 'MISSING'
  | 'OUT_OF_LINEUP'
  | 'UNMAPPED'

export type SportApiPlayerMatchRow = {
  sportapi_player_id: number
  sportapi_player_name: string
  sportapi_short_name?: string | null
  sportapi_position?: string | null
  sportapi_jersey?: number | null
  team_side?: string
  is_missing?: boolean
  api_sports_player_id?: number | null
  api_sports_player_name?: string | null
  player_id?: number | null
  confidence_score: number
  recommendation: MatchRecommendation
  matched_by?: string | null
  score_breakdown?: Record<string, number | boolean>
  from_db_mapping?: boolean
}

export type LineupImpactTopPlayer = {
  player_id?: number
  player_name?: string
  api_sports_player_id?: number | null
  sportapi_player_id?: number | null
  sportapi_player_name?: string | null
  mapping_confidence?: number
  mapping_recommendation?: MatchRecommendation
  team_sot_share?: number
  team_sot_share_pct?: number
  sot_per_90?: number | null
  display_role?: string
  status: PlayerLineupStatus
  status_note?: string
  penalty_weight?: number
  penalty_share?: number
  replacement_player_id?: number | null
  replacement_player_name?: string | null
  replacement_share?: number | null
  replacement_credit?: number
  net_loss_share?: number
  is_top5_sot_team?: boolean
}

/** @deprecated use LineupImpactTopPlayer */
export type LineupImpactPlayerSummary = LineupImpactTopPlayer

export type LineupImpactSideSimulation = {
  team_name: string
  formation?: string | null
  base_sot?: number | null
  adjusted_sot?: number | null
  base_expected_sot?: number | null
  adjusted_sot_simulated?: number | null
  impact_pct?: number | null
  confirmed?: boolean
  lineup_confidence_weight?: number
  factor?: number
  attacking_lineup_factor?: number
  gross_penalty_share?: number
  replacement_credit_share?: number
  net_lineup_loss_share?: number
  net_missing_sot_share?: number
  missing_top5_sot_share?: number
  top_sot_players?: LineupImpactTopPlayer[]
  summary_by_status?: Partial<Record<PlayerLineupStatus, number>>
  reasons?: string[]
  top5_sot_players?: LineupImpactTopPlayer[]
  top5_present?: LineupImpactTopPlayer[]
  top5_missing?: LineupImpactTopPlayer[]
  missing_players_mapped?: unknown[]
  missing_players_unmapped?: unknown[]
  explanation_bullets?: string[]
}

export type LineupImpactSimulationPayload = {
  status: string
  simulation_only: boolean
  used_in_model: boolean
  profiles_missing?: boolean
  sportapi_lineups_available?: boolean
  confirmed?: boolean | null
  confidence_label?: 'alta' | 'media' | 'bassa'
  confidence_reasons?: string[]
  home: LineupImpactSideSimulation
  away: LineupImpactSideSimulation
  player_matching_summary?: Record<string, number>
  sportapi_player_matching?: SportApiPlayerMatchRow[]
  explanation_bullets?: string[]
  defensive_opponent_factor?: null
  note?: string
}
