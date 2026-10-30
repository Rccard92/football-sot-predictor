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

export type JournalSource = 'today' | 'bet_builder' | 'bet_builder_v3'
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
  quota: number
  stake: number | null
  stake_suggested: number | null
  tool: ToolSnapshot
  checklist: Checklist
  analysis_note: string | null
  notes: string | null
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
}

export type EntryInput = {
  today_fixture_id: number
  market_key: string
  quota: number
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
export const getJournalReport = (f: Filters = {}) => request<JournalReport>(`/reports${qs(f)}`)
export const journalExportUrl = (f: Filters = {}) => `${getApiBase()}${BASE}/export.xlsx${qs(f)}`

export const OUTCOME_LABELS: Record<Outcome, string> = { pending: 'In corso', won: 'Vinta', lost: 'Persa', void: 'Nulla' }
export const CHECKLIST_LABELS: Record<ChecklistValue, string> = { favorevole: 'Favorevole', neutro: 'Neutro', contrario: 'Contrario' }

export function formatEuro(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('it-IT', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
