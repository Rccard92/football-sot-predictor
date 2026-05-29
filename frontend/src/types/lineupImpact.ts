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
  player_profile_id?: string | null
  matched_profile_name?: string | null
  confidence_score: number
  recommendation: MatchRecommendation
  matched_by?: string | null
  score_breakdown?: Record<string, number | boolean>
  from_db_mapping?: boolean
  match_reason?: string | null
  reason?: string | null
  shots_on_per90?: number | null
  team_sot_share?: number | null
  shooting_impact_score?: number | null
  reliability_score?: number | null
}

export type LineupPlayerMappingDebugRow = {
  sportapi_player_name?: string
  team_name?: string
  team_side?: string
  role?: string | null
  lineup_status?: string
  matched_profile_name?: string | null
  player_profile_id?: string | null
  api_sports_player_id?: number | null
  match_score?: number | null
  match_status?: MatchRecommendation | string
  shots_on_per90?: number | null
  team_sot_share?: number | null
  shooting_impact_score?: number | null
  reliability_score?: number | null
  reason?: string | null
}

export type PlayerMappingQuality = {
  side?: string
  starters_total?: number
  starters_mapped?: number
  starters_auto_safe?: number
  starters_review?: number
  starters_no_match?: number
  average_match_score?: number
  mapped_with_stats?: number
  mapped_with_shooting_impact?: number
  mapping_confidence?: number
  mapping_quality_label?: 'good' | 'partial' | 'weak' | string
}

export type PlayerLayerUsage = {
  offensive_factor?: number
  defensive_weakness_factor?: number
  opponent_defensive_weakness_factor?: number
  final_factor?: number
  lineup_player_profiles_used?: number
  top_shooters_in_lineup?: number
  top_shooters_missing?: number
  unavailable_players_with_impact?: number
  replacement_credit?: number
  net_loss?: number
  gross_penalty?: number
  impact_explanation?: string | null
}

export type LineupMappingStats = {
  starters_total?: number
  starters_matched_auto_safe?: number
  starters_matched_any?: number
  mapping_rate?: number
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
  player_mapping_quality?: PlayerMappingQuality
  player_layer_usage?: PlayerLayerUsage
}

export type LineupImpactSimulationPayload = {
  status: string
  fixture_id?: number
  simulation_only: boolean
  used_in_model: boolean
  roster_filter_active?: boolean
  profiles_missing?: boolean
  player_profiles_count?: number
  lineup_mapping_stats?: LineupMappingStats
  player_mapping_debug_rows?: LineupPlayerMappingDebugRow[]
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
