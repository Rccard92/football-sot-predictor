/** Diario analisi (dal 30/10/2026): giocate degli analisti, scheda pronostico, progressioni, report. */

import { AdminHttpError } from './api'

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error('VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.')
  }
  return String(raw).replace(/\/+$/, '')
}

const BASE = '/api/analyst-journal'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBase()}${BASE}${path}`, { ...init, credentials: 'include' })
  let body: unknown = null
  if ((res.headers.get('content-type') ?? '').includes('application/json')) {
    try {
      body = await res.json()
    } catch {
      body = null
    }
  }
  if (!res.ok) {
    const o = (body ?? {}) as Record<string, unknown>
    const message = typeof o.detail === 'string' ? o.detail : typeof o.message === 'string' ? o.message : res.statusText
    throw new AdminHttpError(res.status, message, body)
  }
  return body as T
}

function send<T>(method: string, path: string, payload?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}

export type JournalSource = 'today' | 'bet_builder' | 'bet_builder_v3' | 'tabella'
export type ChecklistValue = 'favorevole' | 'neutro' | 'contrario'
export type ChecklistItem = { value: ChecklistValue | null; note: string | null }
export type Checklist = Record<string, ChecklistItem>
export type Outcome = 'pending' | 'won' | 'lost' | 'void'
export type MethodKey = 'cecchino' | 'ceccxino' | 'meraviglia'

export type MarketInfo = { key: string; label: string; group: string }
export type JournalMeta = {
  markets: MarketInfo[]
  checklist: { key: string; label: string }[]
  sources: Record<string, string>
  methods: { key: MethodKey; label: string; defaults: Record<string, number | boolean>; max_bets: number }[]
  can_write: boolean
  is_admin: boolean
  /** Account a cui vanno le giocate di chi e' collegato (null finche' l'accesso di emergenza non ha scritto). */
  user_id: number | null
  /** motivi d'errore automatici (regole di acquisto) e quelli da scegliere nella revisione (07/11/2026) */
  error_codes?: Record<string, string>
  review_tags?: Record<string, string>
  match_types?: string[]
  /** «Prima di salvare» (capitolato del 24/11/2026) */
  answers?: { key: AnswerKey; label: string }[]
  answer_values?: Record<AnswerValue, string>
  risk_note_min?: number
  exception_min?: number
  photos?: { max: number; max_mb: number; caption_min: number }
}

export type AnswerKey = 'assenze' | 'allenatore' | 'motivazione'
export type AnswerValue = 'si' | 'no' | 'nv'
export type Answers = Partial<Record<AnswerKey, AnswerValue>>
/** scheda tecnica salvata con la giocata e non modificabile (modifica 12) */
export type TechSheet = {
  saved_at?: string
  quota?: number
  q?: number | null
  q_at?: string | null
  q_source?: 't75' | 'morning' | null
  quota_cecchino?: number | null
  value?: number | null
  state?: SignState | null
  cecchino_version?: string
  kpi_version?: string | null
  rules_version?: string
  rules_checked?: string[]
  violated?: string[]
  violated_text?: string[]
  notes?: string[]
  exception?: boolean
  exception_reason?: string | null
  alerts?: HeaderAlert[]
}
export type EntryPhoto = { id: number; caption: string; uploaded_at: string | null; after_kickoff: boolean; width: number; height: number; url: string }
export type EntryChange = { field: string; old: string | null; new: string | null; after_kickoff: boolean; at: string | null }

/** Cosa diceva il tool quando la giocata e' stata scelta (dalla pagina di origine). */
export type ToolSnapshot = {
  probability?: number | null
  index_score?: number | null
  engine?: string | null
  label?: string | null
  quota_tool?: number | null
  origin?: string | null
  prob_cecchino?: number | null
  quota_cecchino?: number | null
  quota_book?: number | null
}

export type JournalEntry = {
  id: number
  user_id: number
  user_name: string | null
  cycle_id: number | null
  today_fixture_id: number | null
  match_date: string
  week: string
  kickoff: string | null
  league_name: string | null
  country_name: string | null
  home_team: string
  away_team: string
  source: JournalSource
  source_label: string
  market_key: string
  market_label: string
  market_group: string | null
  /** quota presa dall'analista */
  quota: number
  /** quota presa e CLV (09/11/2026) */
  bookmaker?: string | null
  quota_tool?: number | null
  quota_tool_at?: string | null
  closing_quota?: number | null
  closing_bookmaker?: string | null
  closing_at?: string | null
  /** ok = chiusura letta, nd = non disponibile, null = ancora da leggere */
  closing_status?: 'ok' | 'nd' | null
  closing_note?: string | null
  /** dal 18/11/2026: quota presa x probabilita' di chiusura senza margine - 1 */
  clv?: number | null
  /** vecchia formula: quota presa / quota di chiusura - 1 */
  clv_ratio?: number | null
  /** probabilita' di chiusura senza margine (stesso mercato e bookmaker della chiusura) */
  closing_prob?: number | null
  stake: number | null
  stake_suggested: number | null
  tool: ToolSnapshot
  checklist: Checklist
  analysis_note: string | null
  notes: string | null
  /** nota scritta nella Tabella analisi sulla stessa partita (solo nell'elenco giocate) */
  table_note?: string | null
  /** revisioni dopo la partita, dell'analista e degli amministratori (solo nell'elenco giocate) */
  reviews?: EntryReview[]
  /** regole di acquisto controllate al salvataggio (solo nell'elenco giocate) */
  match_type?: string | null
  quota_cecchino?: number | null
  rule_warnings?: RuleWarning[]
  out_of_rules?: boolean
  error_codes?: string[]
  to_review?: boolean
  minutes_spent: number | null
  outcome: Outcome
  result_ht: string | null
  result_ft: string | null
  profit: number | null
  profit_units: number | null
  locked: boolean
  /** capitolato del 24/11/2026 */
  is_exception?: boolean
  exception_reason?: string | null
  answers?: Answers | null
  risk_note?: string | null
  tech?: TechSheet | null
}

export type FixtureInfo = {
  fixture: {
    today_fixture_id: number
    match_date: string
    kickoff: string | null
    started: boolean
    league_name: string | null
    country_name: string | null
    home_team: string
    away_team: string
    /** quando il tool ha letto le quote del book (09/11/2026) */
    odds_checked_at?: string | null
  }
  markets: (MarketInfo & { quota_book: number | null; prob_cecchino: number | null })[]
  hints: Record<string, string>
  my_entries: JournalEntry[]
}

export type CycleState = {
  method: MethodKey
  method_label: string
  settings: Record<string, number | boolean>
  bankroll_start: number
  bankroll: number
  bets_played: number
  max_bets: number
  won: number
  lost: number
  profit: number
  status: string
  status_label: string
  info: Record<string, unknown>
}

export type Cycle = {
  id: number
  user_id: number
  user_name?: string | null
  name: string
  method: MethodKey
  method_label: string
  status: 'aperta' | 'chiusa'
  notes: string | null
  state: CycleState
  entries_total: number
  pending: number
  pending_stake: number
  settled_count: number
  suggestion?: { stake: number | null; reason: string | null; warning?: string; note?: string }
}

export type ReportRow = {
  entries: number
  settled: number
  won: number
  lost: number
  void: number
  win_pct: number | null
  avg_quota: number | null
  breakeven_pct: number | null
  profit_units: number
  roi_units_pct: number | null
  staked: number
  profit: number
  roi_pct: number | null
  hours: number
  profit_per_hour: number | null
  tool_prob_pct: number | null
  /** CLV (09/11/2026): giocate con la chiusura, CLV medio e quota delle giocate con CLV positivo */
  clv_n?: number
  clv_avg_pct?: number | null
  clv_pos_pct?: number | null
  /** vecchia formula, tenuta a parte dal 18/11/2026 */
  clv_ratio_n?: number
  clv_ratio_avg_pct?: number | null
  clv_ratio_pos_pct?: number | null
}

export type JournalReport = {
  total: ReportRow
  months: (ReportRow & { month: string })[]
  weeks: (ReportRow & { week: string })[]
  month_groups: (ReportRow & { month: string; group: string })[]
  markets: (ReportRow & { market_key: string; label: string; group: string | null })[]
  sources: (ReportRow & { source: string; label: string })[]
  checklist: (ReportRow & { key: string; label: string; value: ChecklistValue })[]
  groups: string[]
  errors?: (ReportRow & { code: string; label: string })[]
  rules?: (ReportRow & { key: 'dentro' | 'fuori'; label: string })[]
  /** quanto vale ogni regola (modifica 11) */
  rule_value?: RuleValue
}

export type RuleGroup = { key: string; label: string; entries: number; settled: number; won: number; lost: number; units: number }
export type RuleValue = {
  groups: RuleGroup[]
  hypothesis: RuleGroup
  /** ipotesi 2: gare sulla carta dal 26/11/2026, verdetto a 100 */
  hypothesis_verdict?: { from: string; target: number; entries: number; settled: number; won: number; lost: number; units: number }
  /** P27 · posizione decisa e P27 · senza obiettivi su due righe */
  alert_rows?: RuleGroup[]
  rule: string | null
  alert: string | null
  rule_filters: string[]
  alert_filters: Record<string, string>
}

export type EntryInput = {
  today_fixture_id: number
  market_key: string
  quota: number
  /** bookmaker della quota presa (obbligatorio dal 09/11/2026) */
  bookmaker: string
  source: JournalSource
  stake?: number | null
  stake_suggested?: number | null
  cycle_id?: number | null
  tool?: ToolSnapshot
  checklist?: Checklist
  analysis_note?: string
  notes?: string
  minutes_spent?: number | null
  /** «Prima di salvare» ed eccezione (24/11/2026) */
  answers?: Answers
  risk_note?: string
  exception?: boolean
  exception_reason?: string
}

export type Filters = { date_from?: string; date_to?: string; user_id?: number | null }

export const getJournalMeta = () => request<JournalMeta>('/meta')
export const listAnalysts = () => request<{ analysts: { id: number; name: string }[] }>('/analysts')
export const getFixtureInfo = (id: number, marketKey?: string) =>
  request<FixtureInfo>(`/fixture/${id}${qs({ market_key: marketKey })}`)
export const listEntries = (f: Filters & { cycle_id?: number; outcome?: Outcome } = {}) =>
  request<{ entries: JournalEntry[] }>(`/entries${qs(f)}`)
export const createEntry = (input: EntryInput) => send<{ entry: JournalEntry }>('POST', '/entries', input)
export const updateEntry = (id: number, input: Partial<EntryInput>) => send<{ entry: JournalEntry }>('PATCH', `/entries/${id}`, input)
export const deleteEntry = (id: number) => send<{ deleted: number }>('DELETE', `/entries/${id}`)
export const getEntry = (id: number) => request<{ entry: JournalEntry; changes: EntryChange[]; photos: EntryPhoto[] }>(`/entries/${id}`)
export const uploadEntryPhoto = (id: number, file: File, caption: string) => {
  const form = new FormData()
  form.append('file', file)
  form.append('caption', caption)
  return request<{ photo: EntryPhoto }>(`/entries/${id}/photos`, { method: 'POST', body: form })
}
export const removeEntryPhoto = (id: number, photoId: number) => send<{ removed: number }>('DELETE', `/entries/${id}/photos/${photoId}`)
/** l'immagine si legge con il cookie di sessione e si mostra come blob (anche quando il sito e l'API sono su domini diversi) */
export async function photoBlobUrl(photo: EntryPhoto): Promise<string> {
  const res = await fetch(`${getApiBase()}${photo.url}`, { credentials: 'include' })
  if (!res.ok) throw new AdminHttpError(res.status, 'Foto non disponibile', null)
  return URL.createObjectURL(await res.blob())
}
/** segno bloccato scelto: si salva sulla carta (modifica 11) */
export const savePaperPlay = (todayFixtureId: number, marketKey: string) =>
  send<{ saved: boolean; id?: number }>('POST', '/paper', { today_fixture_id: todayFixtureId, market_key: marketKey })
export const listCycles = (f: { user_id?: number | null; status?: string } = {}) => request<{ cycles: Cycle[] }>(`/cycles${qs(f)}`)
export const getCycle = (id: number, quota?: number | null) =>
  request<{ cycle: Cycle; entries: JournalEntry[] }>(`/cycles/${id}${qs({ quota: quota ?? undefined })}`)
export const createCycle = (input: { name: string; method: MethodKey; settings: Record<string, number | boolean>; notes?: string }) =>
  send<{ cycle: Cycle }>('POST', '/cycles', input)
export const updateCycle = (id: number, input: Partial<{ name: string; notes: string; status: 'aperta' | 'chiusa'; settings: Record<string, number | boolean> }>) =>
  send<{ cycle: Cycle }>('PATCH', `/cycles/${id}`, input)
// --- Tabella analisi (bozza di Giovanni, dal 05/11/2026) ---

export type TableOutcome = 'V' | 'N' | 'P'
export type TableGame = {
  date: string | null
  opponent_id?: number | null
  opponent: string | null
  opponent_rank: number | null
  home: boolean
  ft: string | null
  ht: string | null
  ft_outcome: TableOutcome | null
  ht_outcome: TableOutcome | null
  bold_ft: boolean
  bold_ht: boolean
  /** dal 18/11/2026: punti a partita dell'avversaria meno i nostri, alla data della gara */
  diff?: number | null
  /** la vecchia differenza in punti (formula del 09/11), per confronto */
  diff_points?: number | null
  /** strong da +0,3 (cornice), weak da -0,3, even in mezzo */
  level?: DiffLevel | null
}
export type DiffLevel = 'strong' | 'even' | 'weak'
export type TableSigns = { ht_games: number; x_pt: number; u15_pt: number; ft_games: number; x: number; u25: number; u35: number }
export type TableBlock =
  | { games: number; enough: false; missing_results?: string[] }
  | {
      games: number
      enough: true
      points: number
      max_points: number
      scored: number
      conceded: number
      ht_games: number
      ht_scored: number
      ht_conceded: number
      results: TableGame[]
      team_rank: number | null
      /** media dei +/- (09/11/2026): sopra 0 calendario duro, sotto 0 facile */
      strength?: number | null
      strength_level?: DiffLevel | null
      /** la vecchia forza media in punti (prima del 18/11/2026) */
      strength_points?: number | null
      signs?: TableSigns
      /** gare gia' passate senza risultato nel nostro archivio (date) */
      missing_results?: string[]
    }
export type TableCards =
  | { games: number; available: false }
  | { games: number; available: true; own: number; opponents: number; own_avg: number; opponents_avg: number }
export type QuotaStatus = 'ok' | 'out' | 'avoid' | 'none'
export type TableQuote = {
  key: string
  label: string
  group: string
  quota: number | null
  quota_cecchino?: number | null
  /** regole di acquisto (07/11/2026): ok si compra, out fuori fascia, avoid segno da evitare, none nessuna regola */
  status?: QuotaStatus
  warnings?: string[]
  /** avviso "forma da gol" su Under 2,5 e Under 1,5 PT (09/11/2026) */
  goal_alert?: boolean
}
export type GoalForm = { goals: number; games: number; avg: number; alert: boolean; threshold: number; markets: string[] }
/** primo tempo della squadra di casa (in casa) e dell'ospite (fuori) insieme (18/11/2026) */
export type PtForm = GoalForm & { x_pt: number; u15_pt: number; x_pct: number; u15_pct: number }
/** indice di affidabilita' dei dati della gara (18/11/2026) */
export type Reliability = { level: 'green' | 'yellow' | 'red'; red: string[]; yellow: string[] }
export type TableBlockKey = 'forma_casa' | 'forma_fuori' | 'forma_totale_casa' | 'forma_totale_fuori'
export type MatchTableRow = {
  today_fixture_id: number
  scan_date: string
  kickoff: string | null
  country: string | null
  league: string | null
  home_team: string
  away_team: string
  eligible: boolean
  balance: { index: number | null; class: string | null } | null
  blocks: Record<TableBlockKey, TableBlock>
  yellows: { home: TableCards; away: TableCards }
  standings_complete: boolean
  home_rank: number | null
  away_rank: number | null
  quotes: TableQuote[]
  /** Equilibrio, Squilibrio, Scala 1X o Scala X2 dalle quote 1-X-2 (regola di Giovanni, solo nel Diario) */
  match_type?: string | null
  my_note: string
  other_notes: { user_name: string | null; note: string }[]
  started: boolean
  /** meno di 3 gare in casa (squadra di casa) o fuori (ospite): non si aggiunge al diario (09/11/2026) */
  editable?: boolean
  not_editable_reason?: string | null
  goal_form?: GoalForm | null
  /** quando il tool ha letto le quote del book (09/11/2026) */
  odds_checked_at?: string | null
  /** controllo dei dati delle squadre (18/11/2026): red = gara esclusa (es. due squadre con lo stesso codice) */
  data_check?: { level: 'ok' | 'red'; problems: string[] }
  /** gara rinviata o spostata rispetto alla fotografia del mattino (18/11/2026) */
  moved?: { status: string; kickoff: string | null } | null
  /** gare di campionato che mancano, compresa questa (18/11/2026) */
  remaining?: { home: Remaining | null; away: Remaining | null }
  pt_form?: PtForm | null
  reliability?: Reliability
  /** seconda lettura Bet365 a 75' dal via (18/11/2026, 8 settimane) */
  odds_move?: OddsMove | null
  /** ultima e prossima gara in tutte le competizioni (18/11/2026) */
  schedule?: { home: TeamSchedule | null; away: TeamSchedule | null } | null
  /** formazioni e indisponibili (18/11/2026) */
  squads?: { home?: TeamSquad; away?: TeamSquad } | null
  /** capitolato del 24/11/2026 */
  evaluation?: RowEvaluation
  computed_at?: string | null
  weather?: WeatherView | null
  close_games?: { code: string; label: string; text: string } | null
  season_end?: SeasonEnd | null
}
export type SignState = 'playable' | 'check' | 'blocked' | 'out'
export type SignReason = { code: string; rule?: string; text: string; short?: string }
export type EvaluatedSign = {
  key: string
  label: string
  group: string
  /** Q: la quota usata dalle regole (seconda lettura se c'e', altrimenti mattino) */
  q: number | null
  q_at: string | null
  q_source: 't75' | 'morning' | null
  morning: number | null
  change: number | null
  prob_book: number | null
  quota_cecchino: number | null
  prob_cecchino: number | null
  value: number | null
  state: SignState
  reasons: SignReason[]
  notes: SignReason[]
}
export type RowEvaluation = {
  signs: EvaluatedSign[]
  counts: Record<SignState, number>
  odds_at: string | null
  second_read: { done: boolean; at: string | null; due: string | null }
}
export type WeatherHour = { at: string; temperature: number | null; precipitation: number | null; wind: number | null; code: number | null; icon: string; text: string }
export type WeatherView = { status: 'ok' | 'nd'; fetched_at: string | null; kickoff?: WeatherHour; hours?: WeatherHour[] }
export type HeaderAlert = { code: string; text: string }
export type TeamMotivation = { status: 'decisa' | 'lotta' | 'salvezza' | 'senza'; text: string; best: number; worst: number; rank: number }
export type SeasonEnd = { code: string; label: string; text: string; home: TeamMotivation | null; away: TeamMotivation | null; alerts: HeaderAlert[] }
export type OddsMoveMarket = {
  key: string
  morning_quota: number | null
  later_quota: number | null
  morning_prob: number
  later_prob: number
  move_points: number
  cecchino_prob: number | null
  /** il mercato si e' mosso dalla parte del Cecchino (null = non giudicabile) */
  toward_cecchino: boolean | null
  /** quota del mattino x probabilita' a T-75 - 1 */
  clv_morning: number | null
}
export type OddsMove = { status: 'ok' | 'nd'; read_at: string | null; markets: OddsMoveMarket[] }
export type ScheduleGame = {
  date: string | null
  kickoff: string | null
  competition: string | null
  league_match: boolean
  opponent: string | null
  home: boolean
  days: number | null
}
export type TeamSchedule = { last: ScheduleGame | null; next: ScheduleGame | null; games_7: number; games_14: number }
export type SquadPlayer = { id: number; name: string | null; pos: string | null; starts?: number; of?: number }
export type TeamSquad = {
  lineups_known: number
  habitual: SquadPlayer[] | null
  injured: { name: string | null; kind: string | null; reason: string | null; starter: boolean }[]
  missing_starters: number
  probable: SquadPlayer[] | null
  history: {
    date: string | null
    opponent?: string | null
    rosa: { complete: boolean; missing: number; text: string; players?: (string | null)[] } | null
    /** dal 26/11/2026: casa/fuori, posizione, forza e risultato della stessa gara della forma */
    home?: boolean
    opponent_rank?: number | null
    level?: DiffLevel | null
    ft?: string | null
    ht?: string | null
    ft_outcome?: TableOutcome | null
  }[]
  /** il fornitore ha dato gli indisponibili per questa gara (altrimenti "n.d.", mai 0) */
  injuries_known?: boolean
}
export type OddsMovesSummary = {
  reads: number
  /** null = seconda lettura fissa (dal 26/11/2026) */
  until: string | null
  markets: {
    key: string
    n: number
    avg_abs_move_points: number | null
    toward_cecchino_pct: number | null
    judged: number
    clv_morning_avg_pct: number | null
    clv_morning_pos_pct: number | null
  }[]
}
export const getOddsMoves = () => request<OddsMovesSummary>('/odds-moves')
/** gare che mancano: esatte dal calendario, o stima con la lunghezza della stagione precedente (season_games);
 *  phase "knockout" = gara a eliminazione diretta, "end" = stagione regolare finita */
export type Remaining = { games: number; exact: boolean; season_games?: number; phase?: 'knockout' | 'end' }
export type MatchTableResponse = {
  day: string
  total: number
  total_day: number
  page: number
  page_size: number
  countries: string[]
  leagues: string[]
  rows: MatchTableRow[]
  can_write: boolean
  match_types?: string[]
  rules_version?: string
  odds_at?: string | null
}
export type MatchTableParams = {
  day?: string
  upcoming?: boolean
  country?: string
  league?: string
  q?: string
  page?: number
  playable?: boolean
  match_type?: string
}

export const getMatchTable = (p: MatchTableParams = {}) =>
  request<MatchTableResponse>(
    `/table${qs({
      day: p.day,
      upcoming: p.upcoming === undefined ? undefined : String(p.upcoming),
      country: p.country,
      league: p.league,
      q: p.q,
      page: p.page,
      playable: p.playable ? 'true' : undefined,
      match_type: p.match_type,
    })}`,
  )
export type StandingRow = {
  rank: number
  team_id: number
  team: string | null
  played: number
  won: number
  drawn: number
  lost: number
  gf: number
  ga: number
  gd: number
  points: number
}
export type StandingsKind = 'total' | 'home' | 'away'
export type MatchStandings = {
  today_fixture_id: number
  league: string | null
  country: string | null
  home_team_id: number
  away_team_id: number
  games: number
  complete: boolean
  tables: Record<StandingsKind, StandingRow[]>
  /** ultime 5 partite delle due squadre (per id squadra): totale, in casa, fuori */
  recent?: Record<string, Record<StandingsKind, TableGame[]>>
  /** classifica alla data della gara: solo gare finite prima di quest'ora (18/11/2026) */
  as_of?: string | null
  /** gare che mancano alle due squadre, per id squadra (18/11/2026) */
  remaining?: Record<string, Remaining | null>
}
export const getMatchStandings = (todayFixtureId: number) => request<MatchStandings>(`/table/standings/${todayFixtureId}`)
export type EntryReview = { user_id: number; user_name: string | null; text: string; tags?: string[]; updated_at: string | null; mine: boolean }
export const saveEntryReview = (entryId: number, text: string, tags?: string[]) =>
  send<{ entry_id: number; review: EntryReview }>('POST', `/entries/${entryId}/review`, { text, tags })

// --- regole di acquisto (07/11/2026) ---
export type RuleWarning = { code: string; text: string }
export type MarketRule = { min?: number; max?: number; cecchino_mult?: number; avoid?: boolean }
export type BuyRules = {
  checklist_min: number
  under_no_squilibrio: boolean
  markets: Record<string, MarketRule>
  /** blocchi del 24/11/2026 */
  r1_pct?: number
  r1_block?: boolean
  r2_home_points_min?: number
  r2_home_block?: boolean
  r2_pt_zero_min?: number
  r2_pt_block?: boolean
  anomaly_pct?: number
}
export type PlayCheck = {
  match_type: string | null
  quota_cecchino: number | null
  warnings: RuleWarning[]
  checklist_warning: RuleWarning | null
  rule: MarketRule | null
  goal_form?: GoalForm | null
  goal_alert?: boolean
  editable?: boolean
  not_editable_reason?: string | null
  /** dal 26/11/2026: stato del segno su Q, quota presa diversa da Q, avvisi della testata */
  sign?: EvaluatedSign | null
  state_label?: string | null
  quota_gap?: { pct: number; text: string } | null
  alerts?: HeaderAlert[]
  rules_version?: string
}
export const checkPlay = (input: { today_fixture_id: number; market_key: string; quota: number | null; checklist?: Checklist }) =>
  send<PlayCheck>('POST', '/check', input)
export const getBuyRules = () => request<{ rules: BuyRules; markets: MarketInfo[]; can_edit: boolean }>('/rules')
export const saveBuyRules = (rules: BuyRules) => send<{ rules: BuyRules }>('POST', '/rules', { rules })
export const saveMatchNote = (todayFixtureId: number, note: string) =>
  send<{ today_fixture_id: number; note: string }>('POST', `/table/notes/${todayFixtureId}`, { note })

export const getJournalReport = (f: Filters & { rule?: string | null; alert?: string | null } = {}) => request<JournalReport>(`/reports${qs(f)}`)
export const journalExportUrl = (f: Filters = {}) => `${getApiBase()}${BASE}/export.xlsx${qs(f)}`

export const OUTCOME_LABELS: Record<Outcome, string> = { pending: 'In corso', won: 'Vinta', lost: 'Persa', void: 'Nulla' }
export const CHECKLIST_LABELS: Record<ChecklistValue, string> = { favorevole: 'Favorevole', neutro: 'Neutro', contrario: 'Contrario' }

export function formatEuro(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('it-IT', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
