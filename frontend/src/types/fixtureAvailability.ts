export type AvailabilityPlayerRow = {
  api_player_id: number | null
  player_name: string
  availability_status: string
  availability_type: string | null
  reason: string | null
  source?: string
  source_label?: string
  source_detail?: string | null
  record_scope?: string
  api_fixture_id?: number | null
  fixture_date?: string | null
  start_date?: string | null
  end_date?: string | null
  date_window?: string
  applicability_reason?: string
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
  applicable_records: AvailabilityPlayerRow[]
  generic_records_not_applied: AvailabilityPlayerRow[]
  unavailable_count: number
  /** @deprecated usa applicable_records */
  players?: AvailabilityPlayerRow[]
}

export type FixtureAvailabilityResponse = {
  status: string
  fixture_id?: number
  api_fixture_id?: number
  season?: number
  fixture_label?: string
  question?: string
  availability_scope?: string
  availability_available?: boolean
  message?: string | null
  fixture_level_count?: number
  team_level_count?: number
  home?: AvailabilityTeamSide
  away?: AvailabilityTeamSide
  quality?: {
    source?: string
    api_live_call?: boolean
    model_impact?: boolean
    note?: string
  }
}

export type AvailabilitySourceStats = {
  called?: boolean
  results_total?: number
  records_matching_upcoming?: number
  error?: string
}

export type AvailabilityProviderReport = {
  called?: boolean
  candidates_total?: number
  applicable_saved?: number
  candidate_not_applied?: number
  players_checked?: number
  api_calls?: number
  error?: string
}

export type ProviderCandidateRow = {
  player_name?: string
  api_player_id?: number | null
  team_name?: string | null
  source?: string
  source_detail?: string
  record_scope?: string
  confidence?: string
  applicability_status?: string
  applicability_reason?: string | null
  availability_status?: string
  availability_type?: string | null
  start_date?: string | null
  end_date?: string | null
}

export type ProviderCandidatesBlock = {
  candidates_from_injuries?: ProviderCandidateRow[]
  candidates_from_sidelined?: ProviderCandidateRow[]
  candidates_applied?: ProviderCandidateRow[]
  candidates_not_applied?: ProviderCandidateRow[]
}

export type AvailabilityUpcomingIngestResponse = {
  status: string
  season?: number
  api_league_id?: number
  fixtures_checked?: number
  upcoming_api_fixture_ids?: number[]
  providers?: {
    api_football_injuries?: AvailabilityProviderReport
    api_football_sidelined?: AvailabilityProviderReport
  }
  sources?: {
    ids_batch?: AvailabilitySourceStats
    league_season_filtered?: AvailabilitySourceStats
    fixture_direct?: AvailabilitySourceStats
  }
  records_saved?: number
  records_updated?: number
  api_calls?: number
  fixtures_with_availability?: {
    fixture_id: number
    api_fixture_id: number
    fixture: string
    records_saved: number
    players?: { player_name: string; api_player_id?: number; source_detail?: string }[]
  }[]
  fixtures_without_availability?: unknown[]
  provider_future_availability_coverage?: 'ok' | 'empty'
  warnings?: string[]
  errors?: unknown[]
}

export type LastAvailabilityUpcoming = {
  last_run_at?: string | null
  sources?: Record<string, AvailabilitySourceStats>
  upcoming_api_fixture_ids?: number[]
  records_matching_this_fixture?: number
  records_saved_this_fixture?: number
  records_from_ids_batch?: number
  records_from_league_season_filtered?: number
  records_from_fixture_direct?: number
  in_last_upcoming_set?: boolean
  provider_future_availability_coverage?: string
  provider_candidates?: ProviderCandidatesBlock
  note?: string
}

export type { ProviderCandidatesBlock as AvailabilityProviderCandidates }

export type AvailabilityIngestSummary = {
  status: string
  season?: number
  league_internal_id?: number
  api_league_id?: number
  fixtures_checked?: number
  teams_checked?: number
  api_calls?: number
  api_calls_by_fixture?: number
  api_calls_by_team?: number
  availability_records_upserted?: number
  records_fixture_level?: number
  records_team_level?: number
  players_matched_to_registry?: number
  players_not_matched_to_registry?: number
  top_shooters_flagged?: unknown[]
  errors?: unknown[]
  by_record_scope?: Record<string, number>
}

export type AvailabilitySeasonSummary = {
  status: string
  season: number
  league_internal_id?: number
  api_league_id?: number
  total_records?: number
  active_records?: number
  inactive_records?: number
  active_with_fixture?: number
  active_with_registry?: number
  by_source?: Record<string, number>
  by_record_scope?: Record<string, number>
}

export type AvailabilityApiCheckBlock = {
  request: string
  results: number
  errors: string[]
  players: Record<string, unknown>[]
}

export type AvailabilityApiRawRecord = {
  fixture_api_id?: number | null
  fixture_date?: string | null
  team_api_id?: number | null
  team_name?: string | null
  player_api_id?: number | null
  player_name?: string | null
  type?: string | null
  reason?: string | null
  parsed_status?: string | null
  parsed_type?: string | null
  source?: string
  raw_json?: Record<string, unknown>
}

export type AvailabilityApiRawListResponse = {
  status: string
  season: number
  league_internal_id?: number
  api_league_id?: number
  request?: string
  results?: number
  errors?: string[]
  records?: AvailabilityApiRawRecord[]
  coverage?: {
    injuries?: boolean
    raw?: Record<string, unknown>
  }
  message?: string
}

export type AvailabilityFixtureFlowDebug = {
  status: string
  season?: number
  message?: string
  fixture_id?: number
  fixture?: {
    fixture_id: number
    api_fixture_id: number
    label: string
    kickoff_at: string
    status: string
    home_team: string
    home_team_id: number
    api_home_team_id: number
    away_team: string
    away_team_id: number
    api_away_team_id: number
  }
  audit_endpoint?: {
    url: string
    records_returned: number
  }
  api_football_expected_request?: {
    fixture_request: string
    api_league_id: number
    note: string
  }
  db_checks?: {
    player_availability_total_for_fixture_api_id: number
    player_availability_total_for_home_team: number
    player_availability_total_for_away_team: number
    fixture_level_records: Record<string, unknown>[]
    manual_fixture_level_records: Record<string, unknown>[]
    manual_team_level_valid_records: Record<string, unknown>[]
    generic_records_not_applied: Record<string, unknown>[]
  }
  applicable_records?: {
    home: Record<string, unknown>[]
    away: Record<string, unknown>[]
  }
  excluded_records?: {
    player_name: string
    team_name: string
    reason_excluded: string
    record_scope: string
    source: string | null
    api_player_id?: number | null
    api_fixture_id?: number | null
  }[]
  diagnosis?: string[]
  last_availability_fetched_at?: string | null
  last_availability_upcoming?: LastAvailabilityUpcoming
  provider_candidates?: ProviderCandidatesBlock
}

export type AvailabilityLiveFixtureCheck = {
  status: string
  season?: number
  fixture_id?: number
  api_fixture_id?: number
  message?: string
  request?: string
  results?: number
  records?: {
    player_name?: string | null
    player_api_id?: number | null
    team_name?: string | null
    team_api_id?: number | null
    type?: string | null
    reason?: string | null
    parsed_status?: string | null
    parsed_type?: string | null
    raw_json?: Record<string, unknown>
  }[]
  errors?: string[]
  note?: string
}

export type AvailabilityAuditMeta = {
  url: string
  httpStatus: number
  durationMs: number
  error?: string
}

export type AvailabilityRawCheckResponse = {
  status: string
  season: number
  league_internal_id?: number
  api_league_id?: number
  league_id?: number
  fixture?: Record<string, unknown>
  coverage?: {
    injuries?: boolean
    lineups?: boolean
    players?: boolean
    fixtures_statistics?: unknown
    raw?: Record<string, unknown>
  }
  api_checks?: {
    by_fixture?: AvailabilityApiCheckBlock
    home_team?: AvailabilityApiCheckBlock
    away_team?: AvailabilityApiCheckBlock
    league_season?: AvailabilityApiCheckBlock
  }
  db_records_for_fixture?: Record<string, unknown>[]
  db_records_for_teams?: Record<string, unknown>[]
  player_search?: {
    query: string
    found_in_api_by_fixture?: boolean
    found_in_api_home_team?: boolean
    found_in_api_away_team?: boolean
    found_in_api_league_season?: boolean
    found_in_db_availability?: boolean
    found_in_player_registry?: boolean
    found_in_player_season_profiles?: boolean
    possible_matches?: Record<string, unknown>[]
  }
  diagnosis?: string[]
}
