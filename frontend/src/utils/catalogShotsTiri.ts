/**
 * Regole sezione «Tiri» (volume conclusioni, non tiri in porta) — solo frontend.
 * `GoalSubsection` è importato come tipo da catalogSections (nessuna logica Goal a runtime).
 */

import type { ModelRelevantField } from '../lib/api'
import type { GoalSubsection } from './catalogSections'

function normPathLocal(f: ModelRelevantField): string {
  const raw = (f.original_json_path || f.json_path || '').toLowerCase()
  return raw.replace(/\[\d+\]/g, '.').replace(/\.+/g, '.').replace(/^\.|\.$/g, '')
}

function shotsBlob(f: ModelRelevantField): string {
  const p = normPathLocal(f)
  const k = (f.key || '').toLowerCase()
  const tail = k.includes('::') ? k.split('::').slice(1).join('::') : k
  return `${p} ${tail} ${(f.technical_name || '').toLowerCase()} ${(f.name_it || '').toLowerCase()} ${(f.endpoint || '').toLowerCase()}`
}

export const CATALOG_SECTION_RULES = {
  tiri: {
    title: 'Tiri',
    locked: false as boolean,
    subtitle:
      'Volume complessivo delle conclusioni: tiri totali, fuori, bloccati e per zona.',
    includeRules: {
      note:
        'Total Shots, shots total/off/blocked, inside/outside box, statistics bracket keys; path statistics.shots.total/off/blocked; escludi on goal / on target / SOT.',
    },
    excludeRules: {
      note: 'Tiri in porta, goal, score, metadati, altre statistiche.',
    },
  },
} as const

export const SHOTS_TIRI_SECTION_SUBTITLE = CATALOG_SECTION_RULES.tiri.subtitle

function isExcludedShotsTiriVolume(blob: string, p: string): boolean {
  if (/on goal|on target|on_target|shots_on|shots on goal|\bsot\b/.test(blob)) return true
  if (/\bgoals\.|\bscore\./.test(p)) return true
  if (
    /corner|booking|card|foul|penalt|passes|pass\.|possession|lineup|startxi|substitute|formation|injur|sidelined|odds|bookmaker|referee|venue|timezone|logo|\.id\b/.test(
      blob,
    )
  )
    return true
  if (blob.includes('goalkeeper')) return true
  if (blob.includes('saves') && !blob.includes('shot')) return true
  if (p.includes('statistics.shots.on')) return true
  return false
}

function isIncludedShotsTiriVolume(blob: string, p: string): boolean {
  if (!blob.includes('shot') && !blob.includes('tiri')) return false

  if (blob.includes('total shots') || blob.includes('total_shots')) return true
  if (blob.includes('blocked shots') || (blob.includes('blocked') && blob.includes('shot'))) return true
  if (blob.includes('shots insidebox') || (blob.includes('insidebox') && blob.includes('shot'))) return true
  if (blob.includes('shots outsidebox') || (blob.includes('outsidebox') && blob.includes('shot'))) return true
  if (blob.includes('shots off goal') || blob.includes('off goal') || blob.includes('shots off')) return true
  if (p.includes('statistics.shots.total') || /\.shots\.total$/.test(p)) return true
  if (p.includes('statistics.shots.off') || p.includes('statistics.shots.blocked')) return true
  if (p.includes('shots.off') || p.includes('shots.blocked') || p.includes('shots.inside') || p.includes('shots.outside'))
    return true
  return false
}

export function matchesShotsTiriSection(f: ModelRelevantField): boolean {
  const p = normPathLocal(f)
  const blob = shotsBlob(f)
  if (isExcludedShotsTiriVolume(blob, p)) return false
  return isIncludedShotsTiriVolume(blob, p)
}

function isPlayerShotsContext(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  const p = normPathLocal(f)
  if (ep.includes('fixtures/players') || ep === 'players' || ep.includes('players/statistics')) return true
  if (p.startsWith('players.') && p.includes('shots')) return true
  return false
}

export function shotsTiriDisplayName(f: ModelRelevantField): string | null {
  if (!matchesShotsTiriSection(f)) return null
  const blob = shotsBlob(f)
  const p = normPathLocal(f)
  const player = isPlayerShotsContext(f)

  if (blob.includes('total shots') || (p.includes('shots.total') && !blob.includes('on goal'))) {
    return player ? 'Tiri totali giocatore' : 'Tiri totali squadra'
  }
  if (blob.includes('shots off goal') || blob.includes('off goal') || p.includes('shots.off'))
    return 'Tiri fuori dallo specchio'
  if (blob.includes('blocked shots') || blob.includes('blocked')) return 'Tiri bloccati'
  if (blob.includes('insidebox') || (blob.includes('inside') && blob.includes('box') && blob.includes('shot')))
    return 'Tiri dentro area'
  if (blob.includes('outsidebox') || (blob.includes('outside') && blob.includes('box') && blob.includes('shot')))
    return 'Tiri fuori area'
  if (p.includes('statistics.shots.blocked')) return 'Tiri bloccati'
  if (p.includes('statistics.shots.off')) return 'Tiri fuori dallo specchio'
  if (p.includes('statistics.shots.total')) return player ? 'Tiri totali giocatore' : 'Tiri totali squadra'
  return 'Indicatore tiri (volume conclusioni)'
}

export function shotsTiriDescription(f: ModelRelevantField): string | null {
  if (!matchesShotsTiriSection(f)) return null
  const blob = shotsBlob(f)
  const p = normPathLocal(f)
  const name = shotsTiriDisplayName(f) || ''

  if (name.includes('Tiri totali squadra') || (name.includes('Tiri totali') && !name.includes('giocatore')))
    return 'Numero complessivo di conclusioni effettuate dalla squadra, indipendentemente dal fatto che siano finite in porta, fuori o siano state bloccate.'
  if (name.includes('fuori dallo specchio') || blob.includes('off goal') || p.includes('shots.off'))
    return 'Conclusioni terminate fuori dalla porta. Sono utili per capire volume offensivo ma non aumentano direttamente i tiri in porta.'
  if (name.includes('bloccati'))
    return 'Conclusioni respinte da un difensore prima di arrivare verso la porta. Indicano pressione offensiva e presenza nella trequarti.'
  if (name.includes('dentro area'))
    return 'Conclusioni effettuate dall’interno dell’area di rigore. Di solito hanno qualità e pericolosità più alta rispetto ai tiri da fuori.'
  if (name.includes('fuori area'))
    return 'Conclusioni effettuate da fuori area. Aumentano il volume tiri ma spesso hanno minore probabilità di diventare goal o tiri pericolosi.'
  if (name.includes('giocatore'))
    return 'Numero di conclusioni effettuate dal singolo giocatore. Utile per player props e per stimare il peso offensivo dei giocatori.'
  if (blob.includes('against') || blob.includes('conceded'))
    return 'Volume di tiri concessi all’avversario, dove applicabile nel catalogo.'
  return 'Indicatore sul volume delle conclusioni (non tiri in porta).'
}

function shotOrganizerBucket(f: ModelRelevantField): number {
  const blob = shotsBlob(f)
  const p = normPathLocal(f)
  if (blob.includes('against') || blob.includes('conceded')) return 3
  if (isPlayerShotsContext(f)) return 2
  if (
    blob.includes('off goal') ||
    blob.includes('blocked') ||
    blob.includes('insidebox') ||
    blob.includes('outsidebox') ||
    p.includes('shots.off') ||
    p.includes('shots.blocked') ||
    p.includes('shots.inside') ||
    p.includes('shots.outside')
  )
    return 1
  return 0
}

const SUB_TITLES: { bucket: number; title: string }[] = [
  { bucket: 0, title: 'Tiri squadra' },
  { bucket: 1, title: 'Tiri per zona / fuori specchio' },
  { bucket: 2, title: 'Tiri giocatore' },
  { bucket: 3, title: 'Tiri concessi' },
]

export function organizeShotsTiriSection(fields: ModelRelevantField[]): {
  allOrdered: ModelRelevantField[]
  subsections: GoalSubsection[]
} {
  const valid = fields.filter((f) => matchesShotsTiriSection(f))
  const decorated = valid.map((f) => ({
    f,
    b: shotOrganizerBucket(f),
    d: shotsTiriDisplayName(f) || normPathLocal(f),
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
