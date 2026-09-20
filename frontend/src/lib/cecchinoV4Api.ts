/**
 * Client di lettura Cecchino V4. Specchia docs/v4/API.md (prefisso `/api/cecchino/v4`).
 * Chi cambia una forma qui aggiorna API.md nello stesso commit.
 */

import { requestJson } from './api'

const V4_BASE = '/api/cecchino/v4'

// --- Vocabolari -------------------------------------------------------------------

export type V4Verdict =
  | 'giocabile'
  | 'prezzo_giusto'
  | 'incertezza_alta'
  | 'non_quotato'
  | 'solo_descrittivo'
  | 'formazioni_non_note'
  | 'quota_anomala'

export type V4UncertaintyLevel = 'bassa' | 'media' | 'alta'
export type V4LineupsStatus = 'non_note' | 'probabili' | 'ufficiali'
export type V4ExamOutcome = 'superato' | 'non_superato' | 'in_attesa'
export type V4ShortlistDayStatus = 'provvisoria' | 'confermata' | 'regolata'
export type V4ShortlistItemStatus = 'provvisoria' | 'confermata' | 'ritirata' | 'regolata'
export type V4PlayResult = 'vinta' | 'persa' | 'void' | 'mezza_vinta' | 'mezza_persa'
export type V4Trend = 'in crescita' | 'in calo' | 'stabile'
export type V4ChallengerStatus = 'candidato' | 'superato' | 'non_superato'
export type V4Side = 'home' | 'away' | 'total'

// --- Riga di mercato ----------------------------------------------------------------

export type V4MarketRow = {
  market_key: string
  family: string
  label: string
  p: number
  lo: number
  hi: number
  p_prudent: number
  quota_bet365: number | null
  quota_betfair: number | null
  quota_used: number | null
  bookmaker_used: string | null
  expected_profit: number | null
  verdict: V4Verdict
  verdict_label: string
  /** Appendice Fase 4: formazioni non note al calcolo, la giocata nasce provvisoria. */
  provisional?: boolean
  /** Appendice Fase 4: false se l'esame E4 della famiglia non e' superato (in osservazione). */
  advised?: boolean
  bookmaker_id?: number | null
  base_rate?: number | null
  stat_exam?: V4ExamOutcome | null
}

// --- Scheda partita -------------------------------------------------------------------

export type V4FixtureResult = {
  ft_home: number
  ft_away: number
  ht_home: number | null
  ht_away: number | null
}

export type V4FixtureCard = {
  id: number
  api_fixture_id: number
  league_code: string
  competition: string
  season_label: string
  kickoff_at: string
  home_team: string
  away_team: string
  /** Stato API-Football: NS, 1H, HT, 2H, FT, PST, ... */
  status: string
  most_likely: { market_key: string; label: string; p: number } | null
  expected_goals: { home: number; away: number } | null
  uncertainty: { score: number; level: V4UncertaintyLevel } | null
  lineups_status: V4LineupsStatus
  best_play: V4MarketRow | null
  /** Motivo dell'astensione (stesse chiavi dei verdetti), null se c'e' una giocata. */
  no_play_reason: string | null
  result: V4FixtureResult | null
}

// --- Ragionamento ------------------------------------------------------------------------

export type V4WhoTeam = {
  team?: string
  attack: number
  defence: number
  attack_rank: number
  defence_rank: number
  teams_in_division: number
  evidence: number
  /** bene | abbastanza | poco */
  known: string
  trend?: V4Trend | null
  home_advantage: number | null
  inherited: string | null
}

export type V4WhoBlock = {
  sentence: string
  home: V4WhoTeam
  away: V4WhoTeam
}

export type V4HowRow = {
  stat: string
  label: string
  home_for: number
  /** null se il payload statistiche non ha `mean_against`. */
  home_against: number | null
  away_for: number
  away_against: number | null
  division_mean: number
  exam?: V4ExamOutcome | null
  home_rank_for?: number | null
  away_rank_for?: number | null
  total?: number | null
}

export type V4HowBlock = {
  sentence: string
  rows: V4HowRow[]
}

/** Forma: scarto tra fatto e atteso nelle ultime partite (nomi ereditati da `specialists.form`). */
export type V4FormSide = {
  matches: number
  goals_delta: number | null
  shots_delta: number | null
  trend?: V4Trend | null
}

export type V4Absence = {
  team: 'home' | 'away'
  player: string
  role: string | null
  impact: number | null
}

export type V4ContextBlock = {
  sentence: string
  form: { home: V4FormSide | null; away: V4FormSide | null } | null
  rest: { home_days: number | null; away_days: number | null; final_phase?: boolean | null } | null
  motivation: { home: string | null; away: string | null } | null
  lineups: { status: V4LineupsStatus; absences: V4Absence[] } | null
  referee: { name: string; cards_per_match: number | null } | null
}

export type V4PredictsBlock = {
  sentence: string
  /** Righe = gol casa 0..max_goals, colonne = gol ospite 0..max_goals (6×6). */
  score_matrix: number[][]
  max_goals: number
  markets: V4MarketRow[]
  most_likely_score?: { home: number; away: number; p: number } | null
  most_likely?: { market_key: string; label: string; p: number } | null
  expected_goals?: { home: number; away: number } | null
}

export type V4WhyBlock = {
  /** null quando non c'e' giocata: `reason` porta il verdetto bloccante e `sentences` la frase "Nessuna giocata: …". */
  play: V4MarketRow | null
  reason?: string | null
  sentences: string[]
  would_change: string[]
}

export type V4AftermathStat = {
  stat: string
  label: string
  expected_home: number | null
  expected_away: number | null
  actual_home: number | null
  actual_away: number | null
}

export type V4AftermathPlay = {
  label: string
  market_key: string
  outcome: V4PlayResult | null
  profit_units: number | null
}

export type V4AftermathBlock = {
  sentence: string
  result: V4FixtureResult | null
  goals: {
    expected_home: number
    expected_away: number
    actual_home: number
    actual_away: number
  }
  stats: V4AftermathStat[]
  play: V4AftermathPlay | null
  luck: string | null
}

export type V4FixtureDetail = {
  fixture: V4FixtureCard
  blocks: {
    who: V4WhoBlock | null
    how: V4HowBlock | null
    context: V4ContextBlock | null
    predicts: V4PredictsBlock | null
    why: V4WhyBlock | null
    aftermath: V4AftermathBlock | null
  }
}

// --- Giorni e lista --------------------------------------------------------------------------

export type V4Day = {
  date: string
  fixtures: number
  plays: number
  finished: number
}

export type V4DaysResponse = { days: V4Day[] }

export type V4FixturesQuery = {
  date: string
  league?: string | null
  only_plays?: boolean
  only_lineups?: boolean
  sort?: 'kickoff' | 'profit'
}

export type V4FixturesResponse = {
  date: string
  items: V4FixtureCard[]
  abstentions: Record<string, number>
}

// --- Shortlist --------------------------------------------------------------------------------

export type V4ShortlistItem = V4MarketRow & {
  fixture_id: number
  home_team: string
  away_team: string
  kickoff_at: string
  rank: number
  top: boolean
  status: V4ShortlistItemStatus
  withdraw_reason: string | null
  result: V4PlayResult | null
  clv: number | null
  /** Appendice Fase 4 */
  id?: number
  league_code?: string
  profit_units?: number | null
  closing_quota?: number | null
  reason?: string[] | string | null
}

export type V4Abstention = {
  reason: string
  /** Etichetta italiana del motivo (Appendice Fase 4). */
  label?: string
  count: number
  examples: string[]
}

export type V4ShortlistResponse = {
  date: string
  status: V4ShortlistDayStatus
  sealed_at: string | null
  digest: string | null
  items: V4ShortlistItem[]
  abstentions: V4Abstention[]
  /** Appendice Fase 4: false se almeno una famiglia e' in osservazione; `banner` la frase da mostrare. */
  advised?: boolean
  banner?: string | null
}

// --- Misura --------------------------------------------------------------------------------------

type V4MeasureGroupBase = {
  plays: number
  profit_units?: number | null
  roi: number | null
  roi_lo: number | null
  roi_hi: number | null
  clv: number | null
  alarm?: boolean | null
}

export type V4MeasureLeagueGroup = V4MeasureGroupBase & { league_code: string }
export type V4MeasureMarketGroup = V4MeasureGroupBase & { market_family: string; label: string }

export type V4MeasureAlert = {
  scope: 'league' | 'market'
  key: string
  plays: number
  alarm_at: string | null
  roi: number | null
  sentence: string
}

export type V4MeasureSummary = {
  by_league: V4MeasureLeagueGroup[]
  by_market: V4MeasureMarketGroup[]
  totals: {
    plays: number
    profit_units?: number | null
    roi: number | null
    roi_lo: number | null
    roi_hi: number | null
    clv: number | null
  }
  alerts: V4MeasureAlert[]
  postmortem?: string[] | null
}

// --- Motore ----------------------------------------------------------------------------------------

export type V4ExamResult = Record<string, unknown>

export type V4Exam = {
  code: string
  title: string
  passed: boolean | null
  preregistration: string
  result: V4ExamResult
  computed_at: string | null
}

export type V4ExamsResponse = { items: V4Exam[] }

export type V4Challenger = {
  name: string
  status: V4ChallengerStatus
  exam: { code?: string; result?: V4ExamResult; computed_at?: string | null } | null
  description?: string | null
}

export type V4ChallengersResponse = { items: V4Challenger[] }

export type V4CoverageRow = {
  league_code: string
  markets: Record<string, boolean>
}

export type V4QualityRow = {
  league_code: string
  fixtures: number
  missing_stats_pct: number
  missing_lineups_pct: number
  missing_odds_pct: number
}

export type V4EngineData = {
  coverage: V4CoverageRow[]
  quality: V4QualityRow[]
  api_budget: { date: string; calls: number; stop_at: number }
  odds_registry: { snapshots_today: number; last_taken_at: string | null }
}

// --- Interfaccia e client reale ---------------------------------------------------------------------

export type CecchinoV4Api = {
  getDays(params: { from: string; days?: number }, signal?: AbortSignal): Promise<V4DaysResponse>
  getFixtures(params: V4FixturesQuery, signal?: AbortSignal): Promise<V4FixturesResponse>
  getFixtureDetail(id: number, signal?: AbortSignal): Promise<V4FixtureDetail>
  getShortlist(date: string, signal?: AbortSignal): Promise<V4ShortlistResponse>
  getMeasureSummary(
    params: { from?: string; to?: string },
    signal?: AbortSignal,
  ): Promise<V4MeasureSummary>
  getExams(signal?: AbortSignal): Promise<V4ExamsResponse>
  getChallengers(signal?: AbortSignal): Promise<V4ChallengersResponse>
  getEngineData(signal?: AbortSignal): Promise<V4EngineData>
}

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === false) continue
    sp.set(k, String(v))
  }
  const q = sp.toString()
  return q ? `?${q}` : ''
}

export async function getV4Days(
  params: { from: string; days?: number },
  signal?: AbortSignal,
): Promise<V4DaysResponse> {
  return requestJson<V4DaysResponse>(
    `${V4_BASE}/days${query({ from: params.from, days: params.days ?? 7 })}`,
    { signal },
  )
}

export async function getV4Fixtures(
  params: V4FixturesQuery,
  signal?: AbortSignal,
): Promise<V4FixturesResponse> {
  return requestJson<V4FixturesResponse>(
    `${V4_BASE}/fixtures${query({
      date: params.date,
      league: params.league,
      only_plays: params.only_plays,
      only_lineups: params.only_lineups,
      sort: params.sort,
    })}`,
    { signal },
  )
}

export async function getV4FixtureDetail(id: number, signal?: AbortSignal): Promise<V4FixtureDetail> {
  return requestJson<V4FixtureDetail>(`${V4_BASE}/fixtures/${id}`, { signal })
}

export async function getV4Shortlist(date: string, signal?: AbortSignal): Promise<V4ShortlistResponse> {
  return requestJson<V4ShortlistResponse>(`${V4_BASE}/shortlist${query({ date })}`, { signal })
}

export async function getV4MeasureSummary(
  params: { from?: string; to?: string },
  signal?: AbortSignal,
): Promise<V4MeasureSummary> {
  return requestJson<V4MeasureSummary>(
    `${V4_BASE}/measure/summary${query({ from: params.from, to: params.to })}`,
    { signal },
  )
}

export async function getV4Exams(signal?: AbortSignal): Promise<V4ExamsResponse> {
  return requestJson<V4ExamsResponse>(`${V4_BASE}/engine/exams`, { signal })
}

export async function getV4Challengers(signal?: AbortSignal): Promise<V4ChallengersResponse> {
  return requestJson<V4ChallengersResponse>(`${V4_BASE}/engine/challengers`, { signal })
}

export async function getV4EngineData(signal?: AbortSignal): Promise<V4EngineData> {
  return requestJson<V4EngineData>(`${V4_BASE}/engine/data`, { signal })
}

export const cecchinoV4Api: CecchinoV4Api = {
  getDays: getV4Days,
  getFixtures: getV4Fixtures,
  getFixtureDetail: getV4FixtureDetail,
  getShortlist: getV4Shortlist,
  getMeasureSummary: getV4MeasureSummary,
  getExams: getV4Exams,
  getChallengers: getV4Challengers,
  getEngineData: getV4EngineData,
}
