import { adminPostJson } from './api'

export type DrawCredibilityAuditRequest = {
  date_from: string
  date_to: string
  competition_id?: number | null
  only_eligible?: boolean
}

export type DrawCredibilityExclusionReason = {
  reason: string
  count: number
  pct_total: number
  pct_finished: number
}

export type DrawCredibilityLeagueRow = {
  country_name: string
  league_name: string
  competition_id: number | null
  total: number
  finished: number
  draws: number
  internal_usable: number
  market_usable: number
  internal_coverage_pct: number
  market_coverage_pct: number
}

export type DrawCredibilityMonthRow = {
  month: string
  total: number
  finished: number
  draws: number
  internal_usable: number
  market_usable: number
}

export type DrawCredibilityDebugSample = {
  today_fixture_id: number
  provider_fixture_id: number
  scan_date: string | null
  home_team: string | null
  away_team: string | null
  league_name: string | null
  reason: string
}

export type DrawCredibilityAuditSummary = {
  total_fixtures: number
  eligible_fixtures: number
  finished_fixtures: number
  finished_with_result: number
  draw_results: number
  non_draw_results: number
  with_cecchino_1x2_odds: number
  with_cecchino_1x2_probabilities: number
  with_complete_cecchino_1x2: number
  with_cecchino_under_2_5: number
  with_cecchino_over_2_5: number
  with_complete_cecchino_goal_pair: number
  with_book_1x2: number
  with_book_under_2_5: number
  with_book_over_2_5: number
  with_complete_book_goal_pair: number
  with_complete_book_markets: number
  usable_internal_research: number
  usable_market_comparison: number
}

export type DrawCredibilityAuditCoverage = {
  cecchino: {
    with_1x2_odds: number
    with_1x2_probabilities: number
    with_complete_1x2: number
    with_under_2_5: number
    with_over_2_5: number
    with_complete_goal_pair: number
    pct_complete_1x2: number
    pct_complete_goal_pair: number
  }
  book: {
    with_1x2: number
    with_under_2_5: number
    with_over_2_5: number
    with_complete_goal_pair: number
    with_complete_markets: number
    pct_complete_markets: number
  }
  research: {
    usable_internal: number
    usable_market_comparison: number
    pct_internal: number
    pct_internal_finished: number
    pct_market: number
    pct_market_finished: number
  }
}

export type DrawCredibilityAuditResponse = {
  status: string
  version: string
  filters: {
    date_from: string
    date_to: string
    competition_id: number | null
    only_eligible: boolean
  }
  summary: DrawCredibilityAuditSummary
  coverage: DrawCredibilityAuditCoverage
  target_distribution: {
    draws: number
    non_draws: number
    draw_rate_pct: number
  }
  exclusion_reasons: DrawCredibilityExclusionReason[]
  by_league: DrawCredibilityLeagueRow[]
  by_month: DrawCredibilityMonthRow[]
  debug_samples: DrawCredibilityDebugSample[]
  warnings: string[]
}

export async function postDrawCredibilityAudit(
  body: DrawCredibilityAuditRequest,
  opts?: { signal?: AbortSignal },
): Promise<DrawCredibilityAuditResponse> {
  return adminPostJson<DrawCredibilityAuditResponse>(
    '/api/admin/cecchino/research/draw-credibility/audit',
    {
      date_from: body.date_from,
      date_to: body.date_to,
      competition_id: body.competition_id ?? null,
      only_eligible: body.only_eligible ?? true,
    },
    opts,
  )
}
