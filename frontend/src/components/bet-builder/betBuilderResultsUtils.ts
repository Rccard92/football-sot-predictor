/** BET-RESULTS-01 — utils Outcome Monitor (frontend). */

import {
  BET_BUILDER_RESULTS_START_DATE,
  type BetBuilderMatchStatus,
  type BetBuilderPredictionOutcome,
  type BetBuilderResultsFixture,
} from '../../lib/cecchinoBetBuilderApi'
import { isIsoDate } from './betBuilderUtils'

export const BET_BUILDER_RESULTS_POLL_ACTIVE_MS = 45_000
export const BET_BUILDER_RESULTS_POLL_SETTLED_MS = 120_000

export type BetBuilderPageView = 'pre-match' | 'results'

export type BetBuilderResultsOutcomeFilter =
  | 'all'
  | 'lost'
  | 'won'
  | 'pending'
  | 'live'

export type BetBuilderResultsSortKey =
  | 'recent'
  | 'kickoff_asc'
  | 'lost_first'
  | 'purchasability_desc'

export type BetBuilderResultsFilterState = {
  dateFrom: string
  dateTo: string
  outcome: BetBuilderResultsOutcomeFilter
  market: 'all' | string
  origin: 'all' | 'price' | 'signals' | 'price_and_signals'
  minPurchasability: number | null
  sort: BetBuilderResultsSortKey
}

export function parseBetBuilderView(value: string | null | undefined): BetBuilderPageView {
  if (value === 'results') return 'results'
  return 'pre-match'
}

export function clampResultsDate(iso: string, todayIso: string): string {
  if (!isIsoDate(iso)) return todayIso < BET_BUILDER_RESULTS_START_DATE
    ? BET_BUILDER_RESULTS_START_DATE
    : todayIso
  if (iso < BET_BUILDER_RESULTS_START_DATE) return BET_BUILDER_RESULTS_START_DATE
  if (iso > todayIso) return todayIso
  return iso
}

export function defaultResultsFilters(todayIso: string): BetBuilderResultsFilterState {
  const day = clampResultsDate(todayIso, todayIso)
  return {
    dateFrom: day,
    dateTo: day,
    outcome: 'all',
    market: 'all',
    origin: 'all',
    minPurchasability: null,
    sort: 'recent',
  }
}

export function outcomeLabel(outcome: BetBuilderPredictionOutcome | string): string {
  switch (outcome) {
    case 'won':
      return 'Vinta'
    case 'lost':
      return 'Persa'
    case 'pending':
      return 'In attesa'
    case 'result_missing':
      return 'Risultato mancante'
    case 'not_evaluable':
      return 'Non valutabile'
    default:
      return outcome
  }
}

export function outcomeBadgeClass(outcome: BetBuilderPredictionOutcome | string): string {
  switch (outcome) {
    case 'won':
      return 'border-emerald-200 bg-emerald-50 text-emerald-900'
    case 'lost':
      return 'border-rose-200 bg-rose-50 text-rose-900'
    case 'pending':
      return 'border-amber-200 bg-amber-50 text-amber-950'
    case 'result_missing':
      return 'border-slate-200 bg-slate-100 text-slate-700'
    case 'not_evaluable':
      return 'border-slate-200 bg-slate-50 text-slate-600'
    default:
      return 'border-slate-200 bg-slate-50 text-slate-700'
  }
}

export function matchStatusLabel(status: BetBuilderMatchStatus | string): string {
  switch (status) {
    case 'live':
      return 'LIVE'
    case 'finished':
      return 'FT'
    case 'upcoming':
      return 'Pre'
    case 'postponed':
      return 'Rinv.'
    case 'cancelled':
      return 'Annull.'
    default:
      return status
  }
}

export function formatScoreLine(
  score: BetBuilderResultsFixture['fixture']['score'] | null | undefined,
  matchStatus?: string,
): string {
  if (!score) return '—'
  const home = score.fulltime_home ?? score.goals_home
  const away = score.fulltime_away ?? score.goals_away
  if (home == null || away == null) {
    if (matchStatus === 'upcoming') return '—'
    return '—'
  }
  return `${home} – ${away}`
}

export function formatWinRate(winRate: number | null | undefined): string {
  if (winRate == null || Number.isNaN(winRate)) return '—'
  return `${(winRate * 100).toFixed(1)}%`
}

export function formatBookQuota(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return 'N/D'
  return n.toFixed(2)
}

export function resultsNeedActivePolling(
  fixtures: BetBuilderResultsFixture[] | null | undefined,
): boolean {
  if (!fixtures || fixtures.length === 0) return false
  return fixtures.some((f) => {
    const status = f.fixture.match_status
    const outcome = f.primary.prediction_outcome
    return status === 'live' || outcome === 'pending' || outcome === 'result_missing'
  })
}

export type ResultsQuickFilterApiParams = {
  outcome?: BetBuilderPredictionOutcome
  match_status?: BetBuilderMatchStatus
}

/**
 * BET-RESULTS-01.2 — traduce il chip UI nei due assi API:
 * match_status (In attesa / Live) vs prediction outcome (Vinte / Perse).
 */
export function mapResultsQuickFilterToApi(
  filter: BetBuilderResultsOutcomeFilter,
): ResultsQuickFilterApiParams {
  switch (filter) {
    case 'pending':
      return { match_status: 'upcoming' }
    case 'live':
      return { match_status: 'live' }
    case 'won':
      return { outcome: 'won' }
    case 'lost':
      return { outcome: 'lost' }
    case 'all':
    default:
      return {}
  }
}

/** Legacy helper — solo asse outcome; preferire mapResultsQuickFilterToApi. */
export function mapOutcomeFilterToApi(
  outcome: BetBuilderResultsOutcomeFilter,
): BetBuilderPredictionOutcome | undefined {
  return mapResultsQuickFilterToApi(outcome).outcome
}

/** BET-RESULTS-01.1 — auto kickoff_asc su «In attesa», override manuale, exit → recent. */
export function applyResultsFiltersPatch(
  prev: BetBuilderResultsFilterState,
  patch: Partial<BetBuilderResultsFilterState>,
  pendingSortAuto: boolean,
  todayIso: string,
): { filters: BetBuilderResultsFilterState; pendingSortAuto: boolean } {
  const next: BetBuilderResultsFilterState = { ...prev, ...patch }
  if (patch.dateFrom) next.dateFrom = clampResultsDate(patch.dateFrom, todayIso)
  if (patch.dateTo) next.dateTo = clampResultsDate(patch.dateTo, todayIso)

  let nextAuto = pendingSortAuto
  const enteringPending =
    patch.outcome !== undefined && patch.outcome === 'pending' && prev.outcome !== 'pending'
  const leavingPending =
    patch.outcome !== undefined && prev.outcome === 'pending' && patch.outcome !== 'pending'
  const sortPatched = patch.sort !== undefined

  if (enteringPending) {
    if (!sortPatched) {
      next.sort = 'kickoff_asc'
      nextAuto = true
    } else {
      nextAuto = false
    }
  } else if (leavingPending) {
    if (nextAuto && next.sort === 'kickoff_asc' && !sortPatched) {
      next.sort = 'recent'
    }
    nextAuto = false
  } else if (sortPatched) {
    nextAuto = false
  }

  return { filters: next, pendingSortAuto: nextAuto }
}
