/** Client API Cecchino V3 — indici a 360 gradi e pagina "Partita per partita". */

import { requestJson } from './api'

const BASE = '/api/admin/cecchino/v3'

export type IndexClass = 'molto_basso' | 'basso' | 'medio' | 'alto' | 'molto_alto'
export type ReliabilityClass = 'alta' | 'media' | 'bassa'

export type EquilibrioIndex = {
  value: number
  favourite: 'home' | 'away' | 'none'
  gap_pp: number
  percentile: number | null
  class: IndexClass | null
}

export type PareggioIndex = {
  prob: number
  league_draw_rate: number | null
  delta_pp: number | null
  percentile: number | null
  class: IndexClass | null
}

export type IntensitaIndex = {
  total: number
  home: number
  away: number
  league_goals_avg: number | null
  ratio: number | null
  p_over_2_5: number
  percentile: number | null
  class: IndexClass | null
}

export type FormaTeam = { gioco: number; risultati: number; matches: number | null } | null

export type MatchIndices = {
  equilibrio: EquilibrioIndex
  pareggio: PareggioIndex
  intensita_goal: IntensitaIndex
  forma: { home: FormaTeam; away: FormaTeam }
  calendario: {
    rest_days_home: number | null
    rest_days_away: number | null
    rest_diff: number | null
    final_phase: boolean
  }
  disciplina: {
    fouls_index_home: number
    fouls_index_away: number
    cards_index_home: number
    cards_index_away: number
    referee: string | null
    referee_goals_index: number
  } | null
  affidabilita: {
    value: number | null
    class: ReliabilityClass | null
    signals: Record<ReliabilityComponent, number>
    contributions: Record<ReliabilityComponent, number> | null
    new_team: boolean
    early_season: boolean
    sign_support: SignSupport
  }
}

export type ReliabilityComponent =
  | 'poca_conoscenza'
  | 'disaccordo_forza'
  | 'disaccordo_gol'
  | 'squadra_nuova'
  | 'inizio_stagione'
  | 'irregolarita'

export type Sign = '1' | 'X' | '2'

export type SignSupport = {
  sign: Sign
  prob: number
  agents_agree: number
  agents_total: number
  specialists: Record<string, Record<Sign, number>>
  form: 'concorde' | 'contraria' | 'neutra' | 'non disponibile'
}

export type CoherenceCheck = {
  code: string
  label: string
  index: string
  increasing?: boolean
  value_format: 'goals' | 'pct' | 'brier_signed' | 'pp_signed'
  rows: Array<{ class: string; n: number; value: number | null; realized?: number | null; expected?: number | null }>
  passed: boolean
}

export type IndexRun = {
  id: number
  source_run_id: number
  engine_version: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  current_step: string | null
  completed_at: string | null
  summary: {
    matches: number
    coherence_checks: CoherenceCheck[]
    reliability_checks?: CoherenceCheck[]
    reliability_passed?: boolean
    reliability_models?: Array<{
      season: string
      trained_on: string[]
      n_train: number
      weights: Record<ReliabilityComponent, number>
      degenerate: boolean
    }>
    sign_support?: Array<{ agents_agree: number; n: number; mean_prob: number; hit_rate: number }>
    all_checks_passed: boolean
    class_distribution: Record<string, Record<string, number>>
  } | null
  error: { message?: string } | null
}

export type MatchListItem = {
  lab_match_id: number
  kickoff_at: string | null
  competition: string
  season_label: string
  home_team: string
  away_team: string
  score: string | null
  eval_eligible: boolean | null
  phase: string | null
  prob_home: number | null
  prob_draw: number | null
  prob_away: number | null
  prob_over_2_5: number | null
  reliability: number | null
  reliability_class: ReliabilityClass | null
  equilibrio: EquilibrioIndex
  pareggio: PareggioIndex
  intensita_goal: IntensitaIndex
}

export type MatchDetail = {
  index_run_id: number
  source_run_id: number
  reliability_passed: boolean
  match: {
    lab_match_id: number
    kickoff_at: string | null
    competition: string
    season_label: string
    home_team: string
    away_team: string
    phase: string
    eval_eligible: boolean
    home_played: number
    away_played: number
    home_remaining: number
    away_remaining: number
  }
  model: {
    lambda_home: number
    lambda_away: number
    rho: number
    ht_share: number
    home_evidence: number
    away_evidence: number
    specialists: Record<string, unknown> | null
  }
  markets: Array<{
    market_key: string
    probability: number | null
    model_odds: number | null
    closing_odds: number | null
    fair_probability: number | null
    won: boolean | null
  }>
  indices: MatchIndices
  result: { ft: string }
}

export async function getIndexRuns(): Promise<{ latest: IndexRun | null; completed: IndexRun | null }> {
  return requestJson(`${BASE}/indices/runs/latest`)
}

export async function startIndexRun(): Promise<IndexRun> {
  return requestJson(`${BASE}/indices/runs`, { method: 'POST' })
}

export async function getMatchFilters(): Promise<{ competitions: string[]; seasons: string[] }> {
  return requestJson(`${BASE}/partite/filtri`)
}

export async function listMatches(params: {
  competition?: string
  season?: string
  team?: string
  reliability?: ReliabilityClass | ''
  limit: number
  offset: number
}): Promise<{ total: number; items: MatchListItem[] }> {
  const qs = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) })
  if (params.competition) qs.set('competition', params.competition)
  if (params.season) qs.set('season_label', params.season)
  if (params.team) qs.set('team', params.team)
  if (params.reliability) qs.set('reliability_class', params.reliability)
  return requestJson(`${BASE}/partite?${qs.toString()}`)
}

export async function getMatchDetail(labMatchId: number): Promise<MatchDetail> {
  return requestJson(`${BASE}/partite/${labMatchId}`)
}

export const INDEX_CLASS_LABELS: Record<IndexClass, string> = {
  molto_basso: 'Molto basso',
  basso: 'Basso',
  medio: 'Medio',
  alto: 'Alto',
  molto_alto: 'Molto alto',
}

export const RELIABILITY_LABELS: Record<ReliabilityClass, string> = {
  alta: 'Alta',
  media: 'Media',
  bassa: 'Bassa',
}

export const RELIABILITY_COMPONENT_LABELS: Record<ReliabilityComponent, string> = {
  poca_conoscenza: 'Poche partite per conoscere le squadre',
  disaccordo_forza: "Specialisti in disaccordo su chi e' piu' forte",
  disaccordo_gol: 'Specialisti in disaccordo sui gol totali',
  squadra_nuova: 'Squadra neopromossa o nuova',
  inizio_stagione: 'Inizio stagione',
  irregolarita: 'Risultati recenti irregolari rispetto alle attese',
}

export const RELIABILITY_COMPONENTS = Object.keys(RELIABILITY_COMPONENT_LABELS) as ReliabilityComponent[]

export const MARKET_LABELS: Record<string, string> = {
  HOME: '1',
  DRAW: 'X',
  AWAY: '2',
  ONE_X: '1X',
  X_TWO: 'X2',
  ONE_TWO: '12',
  OVER_0_5: 'Over 0.5',
  UNDER_0_5: 'Under 0.5',
  OVER_1_5: 'Over 1.5',
  UNDER_1_5: 'Under 1.5',
  OVER_2_5: 'Over 2.5',
  UNDER_2_5: 'Under 2.5',
  OVER_3_5: 'Over 3.5',
  UNDER_3_5: 'Under 3.5',
  HOME_PT: '1 primo tempo',
  DRAW_PT: 'X primo tempo',
  AWAY_PT: '2 primo tempo',
}
