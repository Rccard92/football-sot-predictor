/** Formati, colori e piccoli calcoli della scheda del Diario (capitolato di Giovanni del 24/11/2026). */

import type { EvaluatedSign, MatchTableRow, OddsMoveMarket, RowEvaluation, TableOutcome, TeamSchedule, TeamSquad } from '../../lib/analystJournalApi'

// un colore per ogni significato
export const C = {
  win: { text: '#1F7A45', fill: '#1F9D55', bg: '#E7F6EC' },
  loss: { text: '#B03030', fill: '#D64545', bg: '#FDE8E8' },
  even: { text: '#5B6478', fill: '#8A94A6', bg: '#EEF0F5' },
  warn: { text: '#8A6400', dot: '#C99A00', bg: '#FFF4D6' },
  cmd: { text: '#2457B3', bg: '#E3EDFF' },
  market: { bg: '#F4F5F8' },
  model: { text: '#2457B3', bg: '#EEF4FF' },
  level: '#46506A',
}
export const OUTCOME_FILL: Record<TableOutcome, string> = { V: C.win.fill, N: C.even.fill, P: C.loss.fill }

/** tipo di partita ed equilibrio (modifica 16): mai verde o rosso */
export const CLASS_STYLE: Record<string, { color: string; background: string; borderColor: string }> = {
  Squilibrio: { color: '#B4500A', background: '#FFF1E6', borderColor: '#F3B27A' },
  Equilibrio: { color: '#1F5FA8', background: '#E8F1FB', borderColor: '#9CC0E8' },
  'Equilibrio forte': { color: '#FFFFFF', background: '#1F5FA8', borderColor: '#1F5FA8' },
  'Scala 1X': { color: '#46506A', background: '#F4F5F8', borderColor: '#CFD5E2' },
  'Scala X2': { color: '#46506A', background: '#F4F5F8', borderColor: '#CFD5E2' },
  Transizione: { color: '#46506A', background: '#F4F5F8', borderColor: '#CFD5E2' },
}
export const MATCH_TYPE_HELP =
  'Squilibrio: X almeno 4,00 e la quota più alta fra 1 e 2 è almeno il doppio dell’altra. Equilibrio: rapporto fra 1 e 2 sotto 1,5 e X fino a 3,60. Altrimenti Scala 1X o X2, verso la favorita.'
export const BALANCE_HELP = 'Indice del Cecchino da 0 a 100. Da 90 Equilibrio forte, da 70 Equilibrio, da 50 Transizione, sotto 50 Squilibrio.'

export function q2(v: number | null | undefined): string {
  return v == null ? 'n.d.' : v.toFixed(2).replace('.', ',')
}
export function pct0(v: number | null | undefined): string {
  return v == null ? 'n.d.' : `${Math.round(v * 100)}%`
}
export function signedPct(v: number | null | undefined, digits = 0): string {
  if (v == null) return 'n.d.'
  const n = v * 100
  const text = Math.abs(n).toLocaleString('it-IT', { minimumFractionDigits: digits, maximumFractionDigits: digits })
  const zero = Number(Math.abs(n).toFixed(digits)) === 0
  return zero ? `${text}%` : `${n > 0 ? '+' : '−'}${text}%`
}
export function hhmm(iso: string | null | undefined): string {
  if (!iso) return 'n.d.'
  return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' })
}
export function ddmm(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso.length <= 10 ? `${iso}T12:00:00Z` : iso).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', timeZone: 'Europe/Rome' })
}
export function dec1(v: number | null | undefined): string {
  return v == null ? 'n.d.' : v.toLocaleString('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}
/** "Over 2.5" -> "Over 2,5" */
export function signLabel(label: string): string {
  return label.replace(/(\d)\.(\d)/g, '$1,$2')
}

/** Pulsante «Salva giocata» nella testata (modifica 15): tre stati. */
export function saveButtonFor(sign: EvaluatedSign | null): { tone: 'off' | 'blue' | 'red'; text: string; short: string } {
  if (!sign) return { tone: 'off', text: '+ Salva giocata · scegli un segno', short: '+ Salva · scegli un segno' }
  if (sign.state === 'blocked') {
    const why = sign.reasons[0]?.short ?? sign.reasons[0]?.rule ?? 'regola'
    return { tone: 'red', text: `🔒 ${signLabel(sign.label)} bloccato · ${why}`, short: `🔒 ${signLabel(sign.label)} · ${why}` }
  }
  return { tone: 'blue', text: `+ Salva giocata · ${signLabel(sign.label)} a ${q2(sign.q)}`, short: `+ Salva · ${signLabel(sign.label)} a ${q2(sign.q)}` }
}

/** Quote e Cecchino non concordano: una misura dice Squilibrio e l'altra Equilibrio (o forte). */
export function balanceDisagree(matchType: string | null | undefined, cls: string | null | undefined): boolean {
  const eq = (c: string | null | undefined) => c === 'Equilibrio' || c === 'Equilibrio forte'
  return (matchType === 'Squilibrio' && eq(cls)) || (cls === 'Squilibrio' && eq(matchType))
}

/** ora della quota usata dalle regole: seconda lettura se c'e', altrimenti quella del mattino */
export function readTime(ev: RowEvaluation | undefined): string {
  if (!ev) return 'n.d.'
  return ev.second_read.done ? hhmm(ev.second_read.at) : hhmm(ev.odds_at)
}

/** titolari fuori: «n.d.» se il fornitore non ha dato gli indisponibili (mai 0) */
export function starters(s: TeamSquad | undefined): string {
  if (!s || !s.injuries_known) return 'n.d.'
  return String(s.missing_starters)
}

function scheduleBits(s: TeamSchedule | null | undefined): { rest: number | null; g7: number; next: string | null } | null {
  if (!s) return null
  return { rest: s.last?.days ?? null, g7: s.games_7, next: s.next?.date ?? null }
}

export function calendarSummary(row: MatchTableRow): string {
  const h = scheduleBits(row.schedule?.home)
  const a = scheduleBits(row.schedule?.away)
  if (!h && !a) return 'calendario n.d.'
  const one = (b: ReturnType<typeof scheduleBits>) =>
    b ? `${b.rest != null ? `${b.rest} giorni di riposo` : 'riposo n.d.'}, ${b.g7 === 1 ? '1 gara' : `${b.g7} gare`} negli ultimi 7 giorni${b.next ? `, prossima il ${ddmm(b.next)}` : ''}` : 'n.d.'
  if (h && a && h.rest === a.rest && h.g7 === a.g7 && h.next === a.next) return `entrambe ${one(h)}`
  return `${row.home_team}: ${one(h)} · ${row.away_team}: ${one(a)}`
}

export const MOVE_KEYS = ['HOME', 'DRAW', 'AWAY', 'OVER_1_5', 'OVER_2_5', 'UNDER_2_5', 'UNDER_3_5', 'DRAW_PT', 'UNDER_PT_1_5']

export type MoveRow = { key: string; label: string; morning: number | null; later: number | null; change: number | null; toward: boolean | null }

/** righe del movimento quota (modifica 9): senza seconda lettura la quota a −75' e' «n.d.» */
export function moveRows(row: MatchTableRow): MoveRow[] {
  const m = row.odds_move
  const by = new Map<string, OddsMoveMarket>((m?.status === 'ok' ? m.markets : []).map((x) => [x.key, x]))
  return MOVE_KEYS.map((k) => {
    const q = row.quotes.find((x) => x.key === k)
    const x = by.get(k)
    const morning = x?.morning_quota ?? q?.quota ?? null
    const later = x?.later_quota ?? null
    return { key: k, label: signLabel(q?.label ?? k), morning, later, change: morning && later ? later / morning - 1 : null, toward: x ? x.toward_cecchino : null }
  }).filter((r) => r.morning != null)
}

export function moveSummary(row: MatchTableRow): string {
  const ev = row.evaluation
  if (!ev?.second_read.done) return `seconda lettura Bet365 alle ${hhmm(ev?.second_read.due)}`
  const moved = moveRows(row).filter((r) => r.change != null && Math.abs(r.change) > 0.03).length
  return moved ? `${moved} segni mossi più del 3%` : `seconda lettura Bet365 alle ${hhmm(ev.second_read.at)}`
}
