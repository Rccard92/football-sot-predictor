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
}

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
  /** quota presa / quota di chiusura - 1 */
  clv?: number | null
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
  /** differenza punti avversaria - squadra alla data della gara, a parita' di partite (09/11/2026) */
  diff?: number | null
  /** strong da +3 (cornice), weak da -3, even in mezzo */
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
}
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
}
export type MatchTableParams = { day?: string; upcoming?: boolean; country?: string; league?: string; q?: string; page?: number }

export const getMatchTable = (p: MatchTableParams = {}) =>
  request<MatchTableResponse>(
    `/table${qs({ day: p.day, upcoming: p.upcoming === undefined ? undefined : String(p.upcoming), country: p.country, league: p.league, q: p.q, page: p.page })}`,
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
}
export const getMatchStandings = (todayFixtureId: number) => request<MatchStandings>(`/table/standings/${todayFixtureId}`)
export type EntryReview = { user_id: number; user_name: string | null; text: string; tags?: string[]; updated_at: string | null; mine: boolean }
export const saveEntryReview = (entryId: number, text: string, tags?: string[]) =>
  send<{ entry_id: number; review: EntryReview }>('POST', `/entries/${entryId}/review`, { text, tags })

// --- regole di acquisto (07/11/2026) ---
export type RuleWarning = { code: string; text: string }
export type MarketRule = { min?: number; max?: number; cecchino_mult?: number; avoid?: boolean }
export type BuyRules = { checklist_min: number; under_no_squilibrio: boolean; markets: Record<string, MarketRule> }
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
}
export const checkPlay = (input: { today_fixture_id: number; market_key: string; quota: number | null; checklist?: Checklist }) =>
  send<PlayCheck>('POST', '/check', input)
export const getBuyRules = () => request<{ rules: BuyRules; markets: MarketInfo[]; can_edit: boolean }>('/rules')
export const saveBuyRules = (rules: BuyRules) => send<{ rules: BuyRules }>('POST', '/rules', { rules })
export const saveMatchNote = (todayFixtureId: number, note: string) =>
  send<{ today_fixture_id: number; note: string }>('POST', `/table/notes/${todayFixtureId}`, { note })

export const getJournalReport = (f: Filters = {}) => request<JournalReport>(`/reports${qs(f)}`)
export const journalExportUrl = (f: Filters = {}) => `${getApiBase()}${BASE}/export.xlsx${qs(f)}`

export const OUTCOME_LABELS: Record<Outcome, string> = { pending: 'In corso', won: 'Vinta', lost: 'Persa', void: 'Nulla' }
export const CHECKLIST_LABELS: Record<ChecklistValue, string> = { favorevole: 'Favorevole', neutro: 'Neutro', contrario: 'Contrario' }

export function formatEuro(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('it-IT', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
