/**
 * Regole sezione «Cartellini» — solo frontend.
 * Non importa Goal, Tiri, Tiri in porta né Corner.
 */

import type { ModelRelevantField } from '../lib/api'
import type { GoalSubsection } from './catalogSections'

function normPathLocal(f: ModelRelevantField): string {
  const raw = (f.original_json_path || f.json_path || '').toLowerCase()
  return raw.replace(/\[\d+\]/g, '.').replace(/\.+/g, '.').replace(/^\.|\.$/g, '')
}

function cardsBlob(f: ModelRelevantField): string {
  const p = normPathLocal(f)
  const k = (f.key || '').toLowerCase()
  const tail = k.includes('::') ? k.split('::').slice(1).join('::') : k
  return `${p} ${tail} ${(f.technical_name || '').toLowerCase()} ${(f.name_it || '').toLowerCase()} ${(f.endpoint || '').toLowerCase()} ${(f.recommended_markets || '').toLowerCase()}`
}

export const CATALOG_SECTION_RULES = {
  cartellini: {
    title: 'Cartellini',
    locked: false as boolean,
    subtitle: 'Ammonizioni, espulsioni, eventi disciplinari e futuri mercati cartellini.',
    includeRules: {
      note:
        'Yellow/Red Cards, cards.yellow/red, topyellowcards/topredcards solo statistiche cards, booking odds cartellini.',
    },
    excludeRules: {
      note: 'Falli, rigori, tiri, goal, corner, passaggi, possesso, metadati, eventi generici non card-only.',
    },
  },
} as const

export const CARTELLINI_SECTION_SUBTITLE = CATALOG_SECTION_RULES.cartellini.subtitle

function isOddsLikeField(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  const p = normPathLocal(f)
  return ep.includes('odds') || ep.includes('bookmaker') || p.includes('bookmakers') || p.includes('bets.')
}

function isExcludedCartellini(blob: string, p: string): boolean {
  if (/\bgoals\.|\bscore\.|\.goals\.|\.shots\.|\.passes\.|\.corner\b|\bcorner kicks\b/.test(blob + p)) return true
  if (
    /\bfoul|penalt|shot|on goal|on target|sot\b|goalkeeper|\bsaves\b|possession|lineup|startxi|substitute|formation|injur|sidelined|venue|timezone|logo|\.id\b/.test(
      blob,
    )
  )
    return true
  if (/fixture\.referee|^referee\.|::referee\b/.test(p) && !/card|yellow|red|booking|cartellin/.test(blob)) return true
  return false
}

function isCartelliniOddsMarket(blob: string, p: string): boolean {
  if (!/\bcard|cartellin|booking|ammoniz|espuls|yellow card|red card|yellowcard|redcard/i.test(blob + p)) return false
  if (
    /corner|shot|goal|score|1x2|match winner|btts|handicap(?!.*card)|foul|penalt|passes|possession|first goal/i.test(
      blob + p,
    )
  )
    return false
  return true
}

function isTopCardsEndpoint(ep: string): boolean {
  return ep.includes('topyellowcards') || ep.includes('topredcards')
}

/** Solo statistiche `cards.*` sugli endpoint classifica cartellini (evita goals/passes/shots sullo stesso endpoint). */
function isTopCardsStatsPath(p: string, ep: string): boolean {
  if (!isTopCardsEndpoint(ep)) return false
  return /\.cards\.(yellow|red|yellowred)(\.|$)/.test(p) || p.includes('cards.yellow') || p.includes('cards.red')
}

function isIncludedCartelliniNonOdds(f: ModelRelevantField, blob: string, p: string): boolean {
  const ep = (f.endpoint || '').toLowerCase()

  if (isOddsLikeField(f)) return false

  if (isTopCardsEndpoint(ep)) return isTopCardsStatsPath(p, ep)

  if (/yellow cards|red cards|yellow_card|red_card|event_yellow|event_red|cards\.yellow|cards\.red|cards\.yellowred/.test(blob + p))
    return true
  if (/(^|\.)(statistics\.)?cards\.(yellow|red|yellowred)(\.|$)/.test(p)) return true
  if (/\bbooking\b/.test(blob) && /card|yellow|red|cartellin|ammoniz/.test(blob)) return true

  /** `fixtures/events::type` ecc. sono multi-mercato nel catalogo attuale: non classificare qui. */
  if (ep.includes('fixtures/events')) return false

  return false
}

function isIncludedCartellini(f: ModelRelevantField, blob: string, p: string): boolean {
  if (isOddsLikeField(f)) return isCartelliniOddsMarket(blob, p)
  return isIncludedCartelliniNonOdds(f, blob, p)
}

export function matchesCartelliniSection(f: ModelRelevantField): boolean {
  const p = normPathLocal(f)
  const blob = cardsBlob(f)
  if (isExcludedCartellini(blob, p)) return false
  return isIncludedCartellini(f, blob, p)
}

function isPlayerCardsContext(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  const p = normPathLocal(f)
  if (!ep.includes('fixtures/players')) return false
  return /\.cards\.(yellow|red|yellowred)/.test(p) || p.includes('cards.yellow') || p.includes('cards.red')
}

function extractLine(p: string): string | undefined {
  return p.match(/(\d+(?:\.\d+)?)/)?.[1]
}

export function cartelliniDisplayName(f: ModelRelevantField): string | null {
  if (!matchesCartelliniSection(f)) return null
  const blob = cardsBlob(f)
  const p = normPathLocal(f)
  const ep = (f.endpoint || '').toLowerCase()

  if (isOddsLikeField(f)) {
    const line = extractLine(p)
    if (p.endsWith('.over')) return line ? `Over ${line} cartellini` : 'Quota Over cartellini'
    if (p.endsWith('.under')) return line ? `Under ${line} cartellini` : 'Quota Under cartellini'
    if (line && /\b(value|line|threshold|handicap|total)\b/i.test(blob + p))
      return `Linea cartellini bookmaker (${line})`
    if (line) return `Linea cartellini bookmaker (${line})`
    return 'Mercato cartellini bookmaker'
  }

  if (ep.includes('topyellowcards')) return 'Giocatori con più cartellini gialli'
  if (ep.includes('topredcards')) return 'Giocatori con più cartellini rossi'

  if (isPlayerCardsContext(f)) {
    if (/cards\.red|red cards/.test(blob + p)) return 'Cartellini rossi giocatore'
    return 'Cartellini gialli giocatore'
  }

  if (blob.includes('against') || blob.includes('conceded') || p.includes('against')) {
    if (/red|cards\.red/.test(blob + p)) return 'Cartellini rossi concessi'
    return 'Cartellini gialli concessi'
  }

  if (/red cards|cards\.red/.test(blob + p)) return 'Cartellini rossi squadra'
  return 'Cartellini gialli squadra'
}

export function cartelliniDescription(f: ModelRelevantField): string | null {
  if (!matchesCartelliniSection(f)) return null
  const name = cartelliniDisplayName(f) || ''

  if (name.startsWith('Quota Over') || /^over \d/i.test(name)) {
    return 'Quota offerta dal bookmaker per l’esito Over sul mercato cartellini.'
  }
  if (name.startsWith('Quota Under') || /^under \d/i.test(name)) {
    return 'Quota offerta dal bookmaker per l’esito Under sul mercato cartellini.'
  }
  if (name.startsWith('Linea')) {
    return 'Soglia proposta dal bookmaker per il mercato cartellini, ad esempio Over/Under cartellini totali.'
  }
  if (name === 'Mercato cartellini bookmaker') {
    return 'Mercato bookmaker sui cartellini: verifica nome mercato e linea nei dettagli tecnici.'
  }
  if (name === 'Giocatori con più cartellini gialli') {
    return 'Classifica giocatori ordinata per cartellini gialli; utile per profili a rischio ammonizione.'
  }
  if (name === 'Giocatori con più cartellini rossi') {
    return 'Classifica giocatori ordinata per cartellini rossi; utile per profili a rischio espulsione.'
  }
  if (name.includes('gialli giocatore')) {
    return 'Numero di ammonizioni ricevute dal singolo giocatore. Utile per valutare profili a rischio cartellino.'
  }
  if (name.includes('rossi giocatore')) {
    return 'Numero di espulsioni ricevute dal singolo giocatore.'
  }
  if (name.includes('rossi squadra') || name.includes('rossi concessi')) {
    return 'Numero di espulsioni ricevute dalla squadra nella partita. Dato utile per disciplina e andamento gara.'
  }
  return 'Numero di ammonizioni ricevute dalla squadra nella partita. Utile per costruire un futuro modello sui cartellini.'
}

function organizerBucket(f: ModelRelevantField): number {
  const blob = cardsBlob(f)
  const p = normPathLocal(f)
  const ep = (f.endpoint || '').toLowerCase()

  if (isOddsLikeField(f)) {
    if (p.endsWith('.over')) return 9
    if (p.endsWith('.under')) return 10
    const line = extractLine(p)
    if (line) return 8
    return 11
  }

  if (ep.includes('topyellowcards')) return 6
  if (ep.includes('topredcards')) return 7

  if (isPlayerCardsContext(f)) return /cards\.red|red cards/.test(blob + p) ? 3 : 2

  if (blob.includes('against') || blob.includes('conceded') || p.includes('against'))
    return /red|cards\.red/.test(blob + p) ? 1 : 0

  if (/red cards|cards\.red/.test(blob + p)) return 1
  return 0
}

const SUB_TITLES: { bucket: number; title: string }[] = [
  { bucket: 0, title: 'Cartellini gialli squadra' },
  { bucket: 1, title: 'Cartellini rossi squadra' },
  { bucket: 2, title: 'Cartellini gialli giocatore' },
  { bucket: 3, title: 'Cartellini rossi giocatore' },
  { bucket: 6, title: 'Giocatori con più cartellini gialli' },
  { bucket: 7, title: 'Giocatori con più cartellini rossi' },
  { bucket: 8, title: 'Linea cartellini bookmaker' },
  { bucket: 9, title: 'Quota Over cartellini' },
  { bucket: 10, title: 'Quota Under cartellini' },
  { bucket: 11, title: 'Mercato cartellini bookmaker' },
]

export function organizeCartelliniSection(fields: ModelRelevantField[]): {
  allOrdered: ModelRelevantField[]
  subsections: GoalSubsection[]
} {
  const valid = fields.filter((f) => matchesCartelliniSection(f))
  const decorated = valid.map((f) => ({
    f,
    b: organizerBucket(f),
    d: cartelliniDisplayName(f) || normPathLocal(f),
  }))
  decorated.sort((a, b) => {
    if (a.b !== b.b) return a.b - b.b
    return a.d.localeCompare(b.d, 'it', { sensitivity: 'base' })
  })
  const byBucket = new Map<number, ModelRelevantField[]>()
  for (const { f, b } of decorated) {
    if (!byBucket.has(b)) byBucket.set(b, [])
    byBucket.get(b)!.push(f)
  }
  const subsections: GoalSubsection[] = []
  for (const { bucket, title } of SUB_TITLES) {
    const ps = byBucket.get(bucket)
    if (ps?.length) subsections.push({ title, parameters: ps })
  }
  return { allOrdered: decorated.map((x) => x.f), subsections }
}
