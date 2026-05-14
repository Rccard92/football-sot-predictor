/**
 * Regole sezione «Tiri in porta» (SOT / shots on target) — solo frontend.
 * Non importa logica Goal né il modulo «Tiri» (volume).
 */

import type { ModelRelevantField } from '../lib/api'
import type { GoalSubsection } from './catalogSections'

function normPathLocal(f: ModelRelevantField): string {
  const raw = (f.original_json_path || f.json_path || '').toLowerCase()
  return raw.replace(/\[\d+\]/g, '.').replace(/\.+/g, '.').replace(/^\.|\.$/g, '')
}

function sotBlob(f: ModelRelevantField): string {
  const p = normPathLocal(f)
  const k = (f.key || '').toLowerCase()
  const tail = k.includes('::') ? k.split('::').slice(1).join('::') : k
  return `${p} ${tail} ${(f.technical_name || '').toLowerCase()} ${(f.name_it || '').toLowerCase()} ${(f.endpoint || '').toLowerCase()} ${(f.recommended_markets || '').toLowerCase()}`
}

export const CATALOG_SECTION_RULES = {
  tiri_in_porta: {
    title: 'Tiri in porta',
    locked: false as boolean,
    subtitle:
      'Conclusioni finite nello specchio della porta: dato centrale per la previsione SOT.',
    includeRules: {
      note:
        'Shots on Goal / on target, statistics.shots.on, shots_on_target, mercati bookmaker chiaramente SOT.',
    },
    excludeRules: {
      note: 'Tiri totali, fuori, bloccati, zona, goal, score, metadati, altre statistiche.',
    },
  },
} as const

export const TIRI_IN_PORTA_SECTION_SUBTITLE = CATALOG_SECTION_RULES.tiri_in_porta.subtitle

/** Segmento JSON `shots.on` (API-Football), non la sottostringa "on" in "total". */
const PATH_SHOTS_ON_SEGMENT = /(^|\.)(statistics\.)?shots\.on(\.|$)/

function isOddsLikeField(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  const p = normPathLocal(f)
  return ep.includes('odds') || ep.includes('bookmaker') || p.includes('bookmakers') || p.includes('bets.')
}

function isExcludedTiriInPorta(blob: string, p: string): boolean {
  if (/\bgoals\.|\bscore\./.test(p)) return true
  if (
    /total shots|total_shots|blocked shots|shots insidebox|shots outsidebox|shots off|off goal|off_target|shots_off|insidebox|outsidebox/.test(blob)
  )
    return true
  if (/statistics\.shots\.(total|off|blocked)/.test(p)) return true
  if (/\.shots\.total(\.|$)/.test(p) || /\.shots\.off(\.|$)/.test(p) || /\.shots\.blocked(\.|$)/.test(p)) return true
  if (blob.includes('goalkeeper')) return true
  if (/\bsaves\b/.test(blob) && !/shot|on target|on goal/.test(blob)) return true
  if (
    /corner|booking|card|foul|penalt|passes|pass\.|possession|lineup|startxi|substitute|formation|injur|sidelined|referee|venue|timezone|logo|\.id\b/.test(
      blob,
    )
  )
    return true
  return false
}

function isSotOddsMarket(blob: string, p: string): boolean {
  if (
    !/(shot|tiri).{0,48}(on goal|on target|in porta|sot|on_target)|(on goal|on target|on_target|sot|in porta).{0,48}(shot|tiri)|shots on goal|shots on target|shot on goal|tiri in porta/i.test(
      blob,
    )
  )
    return false
  if (
    /total shot|shots total|corner|cartellin|card |foul|rigor|penalt|goal scorer|first goal|match odds|1x2|double chance|handicap(?!.*shot)/i.test(
      blob + p,
    )
  )
    return false
  return true
}

function isIncludedTiriInPorta(f: ModelRelevantField, blob: string, p: string): boolean {
  if (PATH_SHOTS_ON_SEGMENT.test(p)) return true
  if (p.includes('shots on goal') || p.includes('shots on target') || p.includes('shot on goal')) return true
  if (/shots_on_target|shots_on_goal|shots_ongoal|shots on goal|shots on target|shot on goal|tiri in porta|player shots on target/i.test(blob))
    return true
  if (/\bsot\b/i.test(blob) && /shot|on target|on goal|tiri|specchio/i.test(blob)) return true

  if (isOddsLikeField(f)) {
    return isSotOddsMarket(blob, p)
  }
  return false
}

export function matchesTiriInPortaSection(f: ModelRelevantField): boolean {
  const p = normPathLocal(f)
  const blob = sotBlob(f)
  if (isExcludedTiriInPorta(blob, p)) return false
  return isIncludedTiriInPorta(f, blob, p)
}

function isPlayerMatchContext(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  return ep.includes('fixtures/players')
}

function isPlayerSeasonContext(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  if (ep.includes('fixtures/players')) return false
  if (ep.includes('players/statistics') || ep.startsWith('players/')) return true
  if (ep === 'players') return true
  return false
}

export function tiriInPortaDisplayName(f: ModelRelevantField): string | null {
  if (!matchesTiriInPortaSection(f)) return null
  const blob = sotBlob(f)
  const p = normPathLocal(f)

  if (isOddsLikeField(f)) {
    const line = p.match(/(\d+(?:\.\d+)?)/)?.[1]
    if (p.endsWith('.over')) return line ? `Quota Over tiri in porta (${line})` : 'Quota Over tiri in porta'
    if (p.endsWith('.under')) return line ? `Quota Under tiri in porta (${line})` : 'Quota Under tiri in porta'
    if (/\bover\b/i.test(blob) && !/\bunder\b/i.test(blob))
      return line ? `Quota Over tiri in porta (${line})` : 'Quota Over tiri in porta'
    if (/\bunder\b/i.test(blob) && !/\bover\b/i.test(blob))
      return line ? `Quota Under tiri in porta (${line})` : 'Quota Under tiri in porta'
    return line ? `Linea tiri in porta (${line})` : 'Linea tiri in porta'
  }

  if (blob.includes('against') || blob.includes('conceded') || p.includes('against')) return 'Tiri in porta concessi'

  if (isPlayerSeasonContext(f)) return 'Tiri in porta giocatore stagione'

  if (isPlayerMatchContext(f)) return 'Tiri in porta giocatore'

  return 'Tiri in porta squadra'
}

export function tiriInPortaDescription(f: ModelRelevantField): string | null {
  if (!matchesTiriInPortaSection(f)) return null
  const name = tiriInPortaDisplayName(f) || ''

  if (name.startsWith('Quota Over')) {
    return 'Quota proposta dal bookmaker per scommettere sul superamento della soglia tiri in porta (SOT).'
  }
  if (name.startsWith('Quota Under')) {
    return 'Quota proposta dal bookmaker per scommettere sul mancato superamento della soglia tiri in porta (SOT).'
  }
  if (name.startsWith('Linea')) {
    return 'Soglia proposta dal bookmaker per il mercato tiri in porta, ad esempio Over/Under 6.5 tiri in porta.'
  }
  if (name.includes('concessi')) {
    return 'Numero di tiri nello specchio concessi dalla squadra agli avversari. Utile per valutare la resistenza difensiva.'
  }
  if (name.includes('giocatore stagione')) {
    return 'Totale o media dei tiri in porta del giocatore nella stagione. Utile per costruire metriche come tiri in porta per 90 minuti.'
  }
  if (name.includes('giocatore')) {
    return 'Numero di conclusioni nello specchio effettuate dal singolo giocatore. Serve per stimare l’impatto dei titolari, dei top shooter e delle assenze.'
  }
  return 'Numero di conclusioni della squadra finite nello specchio della porta. È il dato centrale per il modello sui tiri in porta.'
}

function organizerBucket(f: ModelRelevantField): number {
  if (isOddsLikeField(f)) return 4
  const blob = sotBlob(f)
  const p = normPathLocal(f)
  if (blob.includes('against') || blob.includes('conceded') || p.includes('against')) return 1
  if (isPlayerMatchContext(f)) return 2
  if (isPlayerSeasonContext(f)) return 3
  return 0
}

const SUB_TITLES: { bucket: number; title: string }[] = [
  { bucket: 0, title: 'Tiri in porta squadra' },
  { bucket: 1, title: 'Tiri in porta concessi' },
  { bucket: 2, title: 'Tiri in porta giocatore' },
  { bucket: 3, title: 'Tiri in porta giocatore stagione' },
  { bucket: 4, title: 'Quote tiri in porta' },
]

export function organizeTiriInPortaSection(fields: ModelRelevantField[]): {
  allOrdered: ModelRelevantField[]
  subsections: GoalSubsection[]
} {
  const valid = fields.filter((f) => matchesTiriInPortaSection(f))
  const decorated = valid.map((f) => ({
    f,
    b: organizerBucket(f),
    d: tiriInPortaDisplayName(f) || normPathLocal(f),
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
