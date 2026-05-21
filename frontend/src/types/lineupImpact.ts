export type MatchRecommendation = 'AUTO_SAFE' | 'REVIEW' | 'NO_MATCH'

export type PlayerLineupStatus =
  | 'STARTER'
  | 'BENCH'
  | 'MISSING'
  | 'OUT_OF_LINEUP'
  | 'UNMAPPED'

export type RosterPlayerStatus =
  | 'ACTIVE'
  | 'TRANSFERRED_OUT'
  | 'NOT_IN_CURRENT_SQUAD'
  | 'UNKNOWN'

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
  roster_status?: RosterPlayerStatus
  included_as_unknown?: boolean
}

export type LineupImpactExcludedPlayer = {
  player_name?: string | null
  team_sot_share_pct?: number | null
  roster_status?: RosterPlayerStatus
  exclusion_reason?: string
  shots_on_target_per90?: number | null
}

export type LineupImpactDefensivePlayer = {
  player_id?: number
  player_name?: string
  defensive_role?: string
  defensive_importance?: number
  status?: PlayerLineupStatus
  status_note?: string
  defensive_penalty?: number
  defensive_replacement_credit?: number
  net_defensive_loss?: number
  replacement_player_name?: string | null
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
  offensive_lineup_factor?: number
  opponent_defensive_weakness_factor?: number
  factor?: number
  attacking_lineup_factor?: number
  gross_penalty_share?: number
  replacement_credit_share?: number
  net_lineup_loss_share?: number
  net_missing_sot_share?: number
  missing_top5_sot_share?: number
  defensive_weakness_factor?: number
  gross_defensive_loss?: number
  defensive_replacement_credit?: number
  net_defensive_loss?: number
  top_sot_players?: LineupImpactTopPlayer[]
  defensive_key_players?: LineupImpactDefensivePlayer[]
  excluded_players?: LineupImpactExcludedPlayer[]
  summary_by_status?: Partial<Record<PlayerLineupStatus, number>>
  reasons?: string[]
  offensive_reasons?: string[]
  defensive_reasons?: string[]
  roster_sync_hint?: 'ok' | 'missing' | 'stale'
  top5_sot_players?: LineupImpactTopPlayer[]
  top5_present?: LineupImpactTopPlayer[]
  top5_missing?: LineupImpactTopPlayer[]
  missing_players_mapped?: unknown[]
  missing_players_unmapped?: unknown[]
  explanation_bullets?: string[]
}

export type LineupImpactSimulationPayload = {
  status: string
  fixture_id?: number
  simulation_only: boolean
  used_in_model: boolean
  roster_filter_active?: boolean
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
  defensive_opponent_factor?: {
    home_opponent_factor?: number
    away_opponent_factor?: number
  } | null
  note?: string
}
