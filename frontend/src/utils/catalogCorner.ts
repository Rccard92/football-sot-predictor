/**
 * Regole sezione «Corner» — solo frontend.
 * Non importa Goal, Tiri né Tiri in porta.
 */

import type { ModelRelevantField } from '../lib/api'
import type { GoalSubsection } from './catalogSections'

function normPathLocal(f: ModelRelevantField): string {
  const raw = (f.original_json_path || f.json_path || '').toLowerCase()
  return raw.replace(/\[\d+\]/g, '.').replace(/\.+/g, '.').replace(/^\.|\.$/g, '')
}

function cornerBlob(f: ModelRelevantField): string {
  const p = normPathLocal(f)
  const k = (f.key || '').toLowerCase()
  const tail = k.includes('::') ? k.split('::').slice(1).join('::') : k
  return `${p} ${tail} ${(f.technical_name || '').toLowerCase()} ${(f.name_it || '').toLowerCase()} ${(f.endpoint || '').toLowerCase()} ${(f.recommended_markets || '').toLowerCase()}`
}

export const CATALOG_SECTION_RULES = {
  corner: {
    title: 'Corner',
    locked: false as boolean,
    subtitle: 'Calci d’angolo battuti, concessi e possibili mercati bookmaker sui corner.',
    includeRules: {
      note: 'Corner Kicks, corners, corner_kicks, statistiche corner, quote chiaramente corner.',
    },
    excludeRules: {
      note: 'Tiri, goal, score, cartellini, falli, rigori, possesso, passaggi, metadati.',
    },
  },
} as const

export const CORNER_SECTION_SUBTITLE = CATALOG_SECTION_RULES.corner.subtitle

function isOddsLikeField(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  const p = normPathLocal(f)
  return ep.includes('odds') || ep.includes('bookmaker') || p.includes('bookmakers') || p.includes('bets.')
}

function isExcludedCorner(blob: string, p: string): boolean {
  if (/\bgoals\.|\bscore\./.test(p)) return true
  if (
    /shot|shots on|on target|on goal|total shot|sot\b|yellow|red card|booking|card\.|foul|penalt|passes|pass\.|possession|goalkeeper|\bsaves\b/.test(
      blob,
    )
  )
    return true
  if (/lineup|startxi|substitute|formation|injur|sidelined|referee|venue|timezone|logo|\.id\b/.test(blob)) return true
  return false
}

function isCornerOddsMarket(blob: string, p: string): boolean {
  if (!/\bcorner|calci d'angolo|angiolo\b/i.test(blob + p)) return false
  if (
    /shot|on goal|on target|sot\b|total shot|yellow|red card|booking|foul|penalt|passes|possession|1x2|match winner|double chance|goal scorer|first goal|both teams|btts|handicap(?!.*corner)/i.test(
      blob + p,
    )
  )
    return false
  return true
}

function isIncludedCornerNonOdds(blob: string, p: string): boolean {
  if (/corner kicks|corner_kicks|corner kick\b/.test(blob)) return true
  if (/statistics.*corner kicks|corner kicks.*statistics/.test(p) || p.includes('corner kicks')) return true
  if (/(^|\.)(statistics\.)?corners?(\.|$)/.test(p)) return true
  if (/\bcorners?\b/.test(blob) && /kick|statistic|fixture|team|match/.test(blob)) return true
  if (/\bcorner_kicks\b/.test(blob)) return true
  return false
}

function isIncludedCorner(f: ModelRelevantField, blob: string, p: string): boolean {
  if (isOddsLikeField(f)) return isCornerOddsMarket(blob, p)
  return isIncludedCornerNonOdds(blob, p)
}

export function matchesCornerSection(f: ModelRelevantField): boolean {
  const p = normPathLocal(f)
  const blob = cornerBlob(f)
  if (isExcludedCorner(blob, p)) return false
  return isIncludedCorner(f, blob, p)
}

function isPlayerCornerContext(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  const p = normPathLocal(f)
  if (!ep.includes('fixtures/players') && ep !== 'players' && !ep.includes('players/')) return false
  return p.includes('player') || p.includes('players.')
}

function extractLine(p: string): string | undefined {
  return p.match(/(\d+(?:\.\d+)?)/)?.[1]
}

export function cornerDisplayName(f: ModelRelevantField): string | null {
  if (!matchesCornerSection(f)) return null
  const blob = cornerBlob(f)
  const p = normPathLocal(f)

  if (isOddsLikeField(f)) {
    const line = extractLine(p)
    if (p.endsWith('.over')) return line ? `Over ${line} corner` : 'Quota Over corner'
    if (p.endsWith('.under')) return line ? `Under ${line} corner` : 'Quota Under corner'
    if (line && /\b(value|line|threshold|handicap|total)\b/i.test(blob + p))
      return `Linea corner bookmaker (${line})`
    if (line) return `Linea corner bookmaker (${line})`
    return 'Mercato corner bookmaker'
  }

  if (blob.includes('against') || blob.includes('conceded') || p.includes('against')) return 'Corner concessi'

  if (isPlayerCornerContext(f)) return 'Corner giocatore'

  return 'Corner battuti squadra'
}

export function cornerDescription(f: ModelRelevantField): string | null {
  if (!matchesCornerSection(f)) return null
  const name = cornerDisplayName(f) || ''

  if (name.startsWith('Quota Over') || /^over \d/i.test(name)) {
    return 'Quota offerta dal bookmaker per l’esito Over sul mercato corner.'
  }
  if (name.startsWith('Quota Under') || /^under \d/i.test(name)) {
    return 'Quota offerta dal bookmaker per l’esito Under sul mercato corner.'
  }
  if (name.startsWith('Linea')) {
    return 'Soglia proposta dal bookmaker per il mercato corner, ad esempio Over/Under 8.5 corner totali.'
  }
  if (name === 'Mercato corner bookmaker') {
    return 'Mercato bookmaker sui corner: verifica nome mercato, linea e bookmaker nei dettagli tecnici.'
  }
  if (name.includes('concessi')) {
    return 'Numero di calci d’angolo concessi agli avversari. Utile per capire quanto una squadra subisce pressione laterale o difensiva.'
  }
  if (name.includes('giocatore')) {
    return 'Angoli legati al singolo giocatore, se presenti nel catalogo.'
  }
  return 'Numero di calci d’angolo battuti dalla squadra nella partita. È utile per analizzare pressione offensiva, presenza nella trequarti e futuro mercato corner.'
}

function organizerBucket(f: ModelRelevantField): number {
  if (!isOddsLikeField(f)) {
    const blob = cornerBlob(f)
    const p = normPathLocal(f)
    if (blob.includes('against') || blob.includes('conceded') || p.includes('against')) return 1
    return 0
  }
  const p = normPathLocal(f)
  if (p.endsWith('.over')) return 3
  if (p.endsWith('.under')) return 4
  const line = extractLine(p)
  if (line) return 2
  return 5
}

const SUB_TITLES: { bucket: number; title: string }[] = [
  { bucket: 0, title: 'Corner battuti squadra' },
  { bucket: 1, title: 'Corner concessi' },
  { bucket: 2, title: 'Linea corner bookmaker' },
  { bucket: 3, title: 'Quota Over corner' },
  { bucket: 4, title: 'Quota Under corner' },
  { bucket: 5, title: 'Mercato corner bookmaker' },
]

export function organizeCornerSection(fields: ModelRelevantField[]): {
  allOrdered: ModelRelevantField[]
  subsections: GoalSubsection[]
} {
  const valid = fields.filter((f) => matchesCornerSection(f))
  const decorated = valid.map((f) => ({
    f,
    b: organizerBucket(f),
    d: cornerDisplayName(f) || normPathLocal(f),
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
