/**
 * Regole controllate per sezione catalogo (solo frontend).
 * `locked: true` quando una sezione è approvata e non va più modificata negli step successivi.
 */

import type { ModelRelevantField } from '../lib/api'

function normSeg(s: string): string {
  return s
    .toLowerCase()
    .replace(/\[\d+\]/g, '.')
    .replace(/\.+/g, '.')
    .replace(/^\.|\.$/g, '')
}

/** Path JSON normalizzato (come normPath in catalogFieldLabels). */
export function catalogNormJsonPath(f: ModelRelevantField): string {
  return normSeg(f.original_json_path || f.json_path || '')
}

/** Identificativo stabile operativo: key catalogo (il JSON statico non espone `stable_id`). */
export function catalogStableId(f: ModelRelevantField): string {
  return normSeg(f.key || '')
}

export const CATALOG_SECTION_RULES = {
  goal_over_under: {
    title: 'Goal / Over-Under goal',
    locked: false as boolean,
    includeRules: {
      note:
        'goals.home/away, score.(halftime|fulltime|extratime|penalty).home|away, goals.for.*, goals.against.*, biggest.goals.(for|against).* — su path o segmento dopo :: nella key.',
      pathPrefixes: [
        'goals.home',
        'goals.away',
        'score.halftime.',
        'score.fulltime.',
        'score.extratime.',
        'score.penalty.',
        'goals.for.',
        'goals.against.',
        'biggest.goals.for.',
        'biggest.goals.against.',
      ],
    },
    excludeRules: {
      note: 'Arbitro, rigori statistici, tiri, metadati, ecc.; penalty nel path solo se non score.penalty.home|away.',
      substrings: [
        'referee',
        'fixture.referee',
        'cards',
        'yellow',
        'red',
        'fouls',
        'corner',
        'shots',
        'lineups',
        'players',
        'injuries',
        'sidelined',
        'venue',
        'timezone',
        'league.logo',
        'team.logo',
      ],
    },
  },
} as const

/** Path effettivo per le regole: preferisce json_path; se la key ha suffisso più specifico dopo ::, usa il più lungo. */
function pathForGoalRules(f: ModelRelevantField): string {
  const p = catalogNormJsonPath(f)
  const kRaw = f.key || ''
  const afterSep = kRaw.includes('::') ? normSeg(kRaw.split('::').pop() || '') : catalogStableId(f)
  if (!p) return afterSep
  if (!afterSep || afterSep === p) return p
  return p.length >= afterSep.length ? p : afterSep
}

function isExcludedFromGoalOverUnder(f: ModelRelevantField): boolean {
  const p = pathForGoalRules(f)
  const blob = `${p} ${catalogStableId(f)} ${(f.name_it || '').toLowerCase()} ${(f.technical_name || '').toLowerCase()}`
  for (const sub of CATALOG_SECTION_RULES.goal_over_under.excludeRules.substrings) {
    if (blob.includes(sub)) return true
  }
  if (p.includes('penalty')) {
    if (/^score\.penalty\.(home|away)$/.test(p)) return false
    return true
  }
  return false
}

function isIncludedInGoalOverUnder(f: ModelRelevantField): boolean {
  const p = pathForGoalRules(f)
  if (!p) return false
  if (/^goals\.(home|away)$/.test(p)) return true
  if (/^score\.(halftime|fulltime|extratime|penalty)\.(home|away)$/.test(p)) return true
  for (const pre of CATALOG_SECTION_RULES.goal_over_under.includeRules.pathPrefixes) {
    const preNorm = normSeg(pre)
    if (p === preNorm || p.startsWith(preNorm + '.')) return true
  }
  return false
}

/** Campo ammesso nella sezione Goal / Over-Under. */
export function matchesGoalOverUnderSection(f: ModelRelevantField): boolean {
  if (isExcludedFromGoalOverUnder(f)) return false
  return isIncludedInGoalOverUnder(f)
}

const GOAL_DISPLAY_EXACT: Record<string, string> = {
  'goals.home': 'Goal squadra casa',
  'goals.away': 'Goal squadra trasferta',
  'score.halftime.home': 'Goal casa primo tempo',
  'score.halftime.away': 'Goal trasferta primo tempo',
  'score.fulltime.home': 'Goal casa finale',
  'score.fulltime.away': 'Goal trasferta finale',
  'score.extratime.home': 'Goal casa supplementari',
  'score.extratime.away': 'Goal trasferta supplementari',
  'score.penalty.home': 'Rigori segnati casa nella serie finale',
  'score.penalty.away': 'Rigori segnati trasferta nella serie finale',
  'goals.for.total.total': 'Goal fatti totali',
  'goals.against.total.total': 'Goal subiti totali',
  'goals.for.average.total': 'Media goal fatti',
  'goals.against.average.total': 'Media goal subiti',
  'goals.for.total.home': 'Goal fatti in casa',
  'goals.for.total.away': 'Goal fatti in trasferta',
  'goals.against.total.home': 'Goal subiti in casa',
  'goals.against.total.away': 'Goal subiti in trasferta',
  'biggest.goals.for.home': 'Massimo goal fatti in casa',
  'biggest.goals.for.away': 'Massimo goal fatti in trasferta',
  'biggest.goals.against.home': 'Massimo goal subiti in casa',
  'biggest.goals.against.away': 'Massimo goal subiti in trasferta',
}

function goalsUnderOverLabel(p: string): string | null {
  const parts = p.split('.').filter(Boolean)
  const i = parts.indexOf('under_over')
  if (i < 1) return null
  const forAgainst = parts[i - 1]
  if (forAgainst !== 'for' && forAgainst !== 'against') return null
  const line = parts[i + 1]
  if (!line) return null
  let k = i + 2
  let venue = ''
  if (parts[k] === 'home' || parts[k] === 'away') {
    venue = parts[k] === 'home' ? ' in casa' : ' in trasferta'
    k += 1
  }
  const ou = parts[k]
  if (ou !== 'over' && ou !== 'under') return null
  const fa = forAgainst === 'for' ? 'fatti' : 'subiti'
  return `${ou === 'over' ? 'Over' : 'Under'} ${line} goal ${fa}${venue}`.trim()
}

function minuteBandLabel(p: string, forAgainst: 'for' | 'against'): string | null {
  const re = new RegExp(`^goals\\.${forAgainst}\\.minute\\.(.+)\\.(total|percentage)$`)
  const m = p.match(re)
  if (!m) return null
  const band = m[1]
  const kind = m[2] === 'percentage' ? 'Percentuale' : 'Conteggio'
  const dir = forAgainst === 'for' ? 'fatti' : 'subiti'
  return `${kind} goal ${dir} nel minutaggio ${band.replace(/-/g, '–')}`
}

/** Titolo card per campi Goal controllati (null altrimenti). */
export function goalOverUnderDisplayName(f: ModelRelevantField): string | null {
  if (!matchesGoalOverUnderSection(f)) return null
  const p = pathForGoalRules(f)
  if (GOAL_DISPLAY_EXACT[p]) return GOAL_DISPLAY_EXACT[p]
  const ou = goalsUnderOverLabel(p)
  if (ou) return ou
  const mf = minuteBandLabel(p, 'for')
  if (mf) return mf
  const ma = minuteBandLabel(p, 'against')
  if (ma) return ma
  if (p.startsWith('goals.for.minute')) return 'Distribuzione goal fatti per fascia minuto'
  if (p.startsWith('goals.against.minute')) return 'Distribuzione goal subiti per fascia minuto'
  if (p.startsWith('biggest.goals.')) return `Record goal: ${p.replace(/^biggest\.goals\./, '').replace(/\./g, ' ')}`
  if (p.startsWith('goals.for.')) return `Indicatore goal fatti: ${p.replace(/^goals\.for\./, '').replace(/\./g, ' ')}`
  if (p.startsWith('goals.against.')) return `Indicatore goal subiti: ${p.replace(/^goals\.against\./, '').replace(/\./g, ' ')}`
  return `Dato goal: ${p}`
}

function describeUnderOver(p: string): string | null {
  if (!p.includes('under_over')) return null
  const parts = p.split('.').filter(Boolean)
  const i = parts.indexOf('under_over')
  const forAgainst = i > 0 ? parts[i - 1] : ''
  const ou = parts[parts.length - 1]
  const line = parts[i + 1]
  if ((forAgainst !== 'for' && forAgainst !== 'against') || (ou !== 'over' && ou !== 'under') || !line) {
    return 'Indicatore Over/Under sui goal della squadra (linea e contesto nel path).'
  }
  const isOver = ou === 'over'
  const dir = forAgainst === 'for' ? 'segnati' : 'subiti'
  return isOver
    ? `Numero o percentuale di partite in cui la squadra ha ${dir} più di ${line} goal (Over ${line}).`
    : `Numero o percentuale di partite in cui la squadra ha ${dir} meno di ${line} goal (Under ${line}).`
}

/** Descrizione per campi Goal controllati. */
export function goalOverUnderDescription(f: ModelRelevantField): string | null {
  if (!matchesGoalOverUnderSection(f)) return null
  const p = pathForGoalRules(f)
  const du = describeUnderOver(p)
  if (du) return du
  if (p === 'goals.for.total.total') return 'Numero totale di goal segnati dalla squadra nella stagione.'
  if (p === 'goals.against.total.total') return 'Numero totale di goal concessi dalla squadra nella stagione.'
  if (p === 'goals.for.average.total') return 'Media dei goal segnati dalla squadra per partita.'
  if (p === 'goals.against.average.total') return 'Media dei goal concessi dalla squadra per partita.'
  if (p.startsWith('score.halftime.') || p.startsWith('score.fulltime.') || p.startsWith('score.extratime.')) {
    return 'Goal nel punteggio della singola partita (frazione temporale indicata nel path).'
  }
  if (/^score\.penalty\.(home|away)$/.test(p)) {
    return 'Goal dalla sequenza di rigori a fine partita (tabellino shootout), non statistiche rigori stagionali.'
  }
  if (/^goals\.(home|away)$/.test(p)) return 'Goal totali segnati dalla squadra casa o trasferta nella partita.'
  if (p.includes('minute')) return 'Distribuzione temporale dei goal (fasce di minuto) con conteggi o percentuali.'
  if (p.startsWith('biggest.goals.for.'))
    return 'Valore massimo di goal segnati in una singola partita (sotto-contesto home/away se presente).'
  if (p.startsWith('biggest.goals.against.'))
    return 'Valore massimo di goal subiti in una singola partita (sotto-contesto home/away se presente).'
  if (p.startsWith('goals.for.total'))
    return 'Goal segnati dalla squadra nel sotto-contesto stagionale (totale, casa o trasferta).'
  if (p.startsWith('goals.against.total'))
    return 'Goal concessi dalla squadra nel sotto-contesto stagionale (totale, casa o trasferta).'
  return `Metrica legata a goal o punteggio: ${p}.`
}

const SUB_TITLES: { bucket: number; title: string }[] = [
  { bucket: 0, title: 'Goal partita e punteggio' },
  { bucket: 2, title: 'Goal fatti (stagione)' },
  { bucket: 3, title: 'Goal subiti (stagione)' },
  { bucket: 4, title: 'Medie goal' },
  { bucket: 5, title: 'Over/Under goal fatti' },
  { bucket: 6, title: 'Over/Under goal subiti' },
  { bucket: 7, title: 'Goal per fascia di minuto' },
  { bucket: 8, title: 'Record (massimi goal)' },
]

function goalSortBucket(p: string): number {
  if (/^score\./.test(p) || /^goals\.(home|away)$/.test(p)) return 0
  if (p.startsWith('goals.for.')) {
    if (p.includes('under_over')) return 5
    if (p.includes('minute')) return 7
    if (p.includes('average')) return 4
    if (p.includes('total')) return 2
    return 2
  }
  if (p.startsWith('goals.against.')) {
    if (p.includes('under_over')) return 6
    if (p.includes('minute')) return 7
    if (p.includes('average')) return 4
    if (p.includes('total')) return 3
    return 3
  }
  if (p.startsWith('biggest.goals.')) return 8
  return 9
}

export type GoalSubsection = { title: string; parameters: ModelRelevantField[] }

export function organizeGoalOverUnderSection(fields: ModelRelevantField[]): {
  allOrdered: ModelRelevantField[]
  subsections: GoalSubsection[]
} {
  const valid = fields.filter((f) => matchesGoalOverUnderSection(f))
  const decorated = valid.map((f) => {
    const p = pathForGoalRules(f)
    return { f, p, b: goalSortBucket(p), d: goalOverUnderDisplayName(f) || p }
  })
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
  const rest = byBucket.get(9)
  if (rest?.length) subsections.push({ title: 'Altri indicatori goal', parameters: rest })
  return { allOrdered: decorated.map((x) => x.f), subsections }
}
