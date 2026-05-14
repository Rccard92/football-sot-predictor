/**
 * Etichette e gruppi statistici per il catalogo model-relevant (solo frontend).
 * Inferenza da json_path, endpoint, name_it, ecc. — non modifica i dati sorgente.
 */

import type { ModelRelevantField } from '../lib/api'
import {
  matchesShotsTiriSection,
  organizeShotsTiriSection,
  SHOTS_TIRI_SECTION_SUBTITLE,
  shotsTiriDescription,
  shotsTiriDisplayName,
} from './catalogShotsTiri'
import {
  matchesTiriInPortaSection,
  organizeTiriInPortaSection,
  TIRI_IN_PORTA_SECTION_SUBTITLE,
  tiriInPortaDescription,
  tiriInPortaDisplayName,
} from './catalogTiriInPorta'
import {
  CARTELLINI_SECTION_SUBTITLE,
  cartelliniDescription,
  cartelliniDisplayName,
  matchesCartelliniSection,
  organizeCartelliniSection,
} from './catalogCartellini'
import {
  CORNER_SECTION_SUBTITLE,
  cornerDescription,
  cornerDisplayName,
  matchesCornerSection,
  organizeCornerSection,
} from './catalogCorner'
import {
  goalOverUnderDescription,
  goalOverUnderDisplayName,
  matchesGoalOverUnderSection,
  organizeGoalOverUnderSection,
  type GoalSubsection,
} from './catalogSections'

export type SemanticGroupId =
  | 'tiri'
  | 'tiri_in_porta'
  | 'goal_over_under'
  | 'corner'
  | 'cartellini'
  | 'falli'
  | 'rigori'
  | 'passaggi_possesso'
  | 'parate_portieri'
  | 'formazioni_giocatori'
  | 'infortuni'
  | 'classifica_motivazione'
  | 'quote_bookmaker'
  | 'contesto_tecnico'
  | 'altri'

export const SEMANTIC_GROUP_ORDER: SemanticGroupId[] = [
  'tiri_in_porta',
  'tiri',
  'goal_over_under',
  'corner',
  'cartellini',
  'falli',
  'rigori',
  'passaggi_possesso',
  'parate_portieri',
  'formazioni_giocatori',
  'infortuni',
  'classifica_motivazione',
  'quote_bookmaker',
  'contesto_tecnico',
  'altri',
]

const TITLES: Record<SemanticGroupId, string> = {
  tiri: 'Tiri',
  tiri_in_porta: 'Tiri in porta',
  goal_over_under: 'Goal / Over-Under goal',
  corner: 'Corner',
  cartellini: 'Cartellini',
  falli: 'Falli',
  rigori: 'Rigori',
  passaggi_possesso: 'Passaggi / possesso',
  parate_portieri: 'Parate / portieri',
  formazioni_giocatori: 'Formazioni / giocatori',
  infortuni: 'Infortuni / indisponibili',
  classifica_motivazione: 'Classifica / motivazione',
  quote_bookmaker: 'Quote bookmaker',
  contesto_tecnico: 'Contesto tecnico / fonti derivate',
  altri: 'Altri',
}

export function getSemanticGroupTitle(id: SemanticGroupId): string {
  return TITLES[id] ?? id
}

/** Path normalizzato per matching (minuscolo, indici array ignorati). */
export function normPath(f: ModelRelevantField): string {
  const raw = (f.original_json_path || f.json_path || '').toLowerCase()
  return raw.replace(/\[\d+\]/g, '.').replace(/\.+/g, '.').replace(/^\.|\.$/g, '')
}

function blob(f: ModelRelevantField): string {
  const p = normPath(f)
  const ep = (f.endpoint || '').toLowerCase()
  const ni = (f.name_it || '').toLowerCase()
  const tn = (f.technical_name || '').toLowerCase()
  const mk = (f.recommended_markets || '').toLowerCase()
  return `${p} ${ep} ${ni} ${tn} ${mk}`
}

function isQuoteContext(f: ModelRelevantField): boolean {
  const ep = (f.endpoint || '').toLowerCase()
  if (ep.includes('odds') || ep.includes('bookmakers')) return true
  const p = normPath(f)
  if (p.includes('bookmakers') || p.includes('bets.') || p.includes('odds.')) return true
  return false
}

function isContestoPath(p: string, ep: string): boolean {
  if (/fixture\.(date|timestamp|timezone|periods)/.test(p)) return true
  if (/fixture\.status/.test(p)) return true
  if (/league\.(round|season)/.test(p)) return true
  if (/\bround\b/.test(p) && ep.includes('fixture')) return true
  if (p.includes('venue') && ep === 'fixtures') return true
  return false
}

export function getCatalogFieldGroup(field: ModelRelevantField): SemanticGroupId {
  const p = normPath(field)
  const ep = (field.endpoint || '').toLowerCase()
  const b = blob(field)

  if (ep.includes('injur') || b.includes('injur') || ep.includes('sidelined') || b.includes('sidelined')) {
    return 'infortuni'
  }

  if (ep.includes('standing') || /\brank\b/.test(p) || p.includes('points') || p.includes('standings')) {
    if (/\b(form|played|wins|draws|lose|goalsdiff|description|status)\b/.test(p) || p.includes('league')) {
      return 'classifica_motivazione'
    }
    if (p.includes('team') && (p.includes('rank') || p.includes('points'))) return 'classifica_motivazione'
  }
  if (ep.includes('standing') || p.includes('standing')) return 'classifica_motivazione'

  if (matchesTiriInPortaSection(field)) return 'tiri_in_porta'

  if (matchesCornerSection(field)) return 'corner'

  if (matchesCartelliniSection(field)) return 'cartellini'

  if (isQuoteContext(field)) return 'quote_bookmaker'

  if (matchesShotsTiriSection(field)) return 'tiri'

  if (ep.includes('lineup') || p.includes('startxi') || p.includes('substitute') || p.includes('formation')) {
    return 'formazioni_giocatori'
  }
  if (ep.includes('players') || ep.includes('player') || ep.includes('squads')) {
    if (!p.includes('odds') && !ep.includes('odds')) return 'formazioni_giocatori'
  }

  if (
    p.includes('goalkeeper') ||
    p.includes('goal keeper') ||
    (p.includes('saves') && !p.includes('shots')) ||
    p.includes('clean_sheet') ||
    p.includes('cleansheet')
  ) {
    return 'parate_portieri'
  }

  if (p.includes('possession') || p.includes('passes') || p.includes('pass accuracy') || p.includes('key passes')) {
    return 'passaggi_possesso'
  }
  if (p.includes('total passes') || p.includes('passes accurate')) return 'passaggi_possesso'

  if (
    (p.includes('penalty') || ep.includes('penalt')) &&
    !/^score\.penalty\.(home|away)$/.test(p)
  ) {
    return 'rigori'
  }

  if (p.includes('foul')) return 'falli'

  if (matchesGoalOverUnderSection(field)) return 'goal_over_under'

  if (field.classification === 'SORGENTE_DERIVATA_TECNICA' || field.selectable === false) {
    if (isContestoPath(p, ep)) return 'contesto_tecnico'
    if (ep.includes('lineup') || p.includes('player')) return 'formazioni_giocatori'
    return 'contesto_tecnico'
  }

  if (isContestoPath(p, ep)) return 'contesto_tecnico'

  const area = (field.area || '').toLowerCase()
  if (area.includes('quote') || area.includes('odd')) return 'quote_bookmaker'
  if (area.includes('infortun')) return 'infortuni'
  if (area.includes('classifica') || area.includes('standing')) return 'classifica_motivazione'
  if (area.includes('formazion') || area.includes('giocator')) return 'formazioni_giocatori'
  if (area.includes('corner')) {
    if (matchesCornerSection(field)) return 'corner'
    return 'altri'
  }
  if (area.includes('cartellin') || area.includes('card') || area.includes('ammoniz') || area.includes('espuls')) {
    if (matchesCartelliniSection(field)) return 'cartellini'
    return 'altri'
  }
  if (area.includes('rigor') || area.includes('penalt')) return 'rigori'
  if (area.includes('tiri') || area.includes('shots')) {
    if (matchesTiriInPortaSection(field)) return 'tiri_in_porta'
    if (matchesShotsTiriSection(field)) return 'tiri'
    return 'altri'
  }

  return 'altri'
}

const PENALTY_NAMES: Record<string, string> = {
  'penalty.total': 'Rigori totali calciati',
  'penalty.scored.total': 'Rigori segnati totali',
  'penalty.scored.percentage': 'Percentuale rigori segnati',
  'penalty.missed.total': 'Rigori sbagliati totali',
  'penalty.missed.percentage': 'Percentuale rigori sbagliati',
  'penalty.won': 'Rigori procurati',
  'penalty.committed': 'Rigori causati',
  'penalty.saved': 'Rigori parati',
}

function penaltyDisplayName(f: ModelRelevantField): string | null {
  const p = normPath(f)
  for (const [k, v] of Object.entries(PENALTY_NAMES)) {
    if (p === k || p.endsWith('.' + k) || p.includes('::' + k) || p.endsWith(k)) return v
  }
  return null
}

/** goals.for.under_over.1.5.home.over → "Over 1.5 goal fatti in casa" */
function goalsUnderOverDisplay(p: string): string | null {
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

function scoreDisplay(p: string): string | null {
  const m = p.match(/^score\.(halftime|fulltime|extratime)\.(home|away)$/)
  if (!m) return null
  const phase = m[1] === 'halftime' ? 'primo tempo' : m[1] === 'fulltime' ? 'finale' : 'supplementari'
  const side = m[2] === 'home' ? 'casa' : 'trasferta'
  return `Goal ${side} ${phase}`
}

function goalsScorePathDisplay(p: string): string | null {
  if (p.includes('goals.for.minute') || p.match(/goals\.for\.minute/)) return 'Goal fatti per fascia minuto'
  if (p.includes('goals.against.minute')) return 'Goal subiti per fascia minuto'
  if (p.match(/goals\.for\.total/)) return 'Goal fatti totali'
  if (p.match(/goals\.against\.total/)) return 'Goal subiti totali'
  if (p.match(/goals\.for\.average/)) return 'Media goal fatti'
  if (p.match(/goals\.against\.average/)) return 'Media goal subiti'
  return null
}

const GENERIC_BAD = /^(over|under|home|away|total|percentage)$/i

function shotsDisplay(p: string, nameIt: string): string | null {
  const s = p.toLowerCase()
  if (s.includes('blocked')) return 'Tiri bloccati'
  if (s.includes('inside') && s.includes('box')) return 'Tiri dentro area'
  if (s.includes('outside') && s.includes('box')) return 'Tiri fuori area'
  if (s.includes('total shots') || (s.includes('shots') && s.includes('total'))) return 'Tiri totali'
  if (GENERIC_BAD.test(nameIt.trim()) && s.includes('shot')) return 'Tiri (dettaglio nel path)'
  return null
}

function foulsDisplay(p: string): string | null {
  const s = p.toLowerCase()
  if (s.includes('committed') && s.includes('player')) return 'Falli commessi dal giocatore'
  if (s.includes('drawn') && s.includes('player')) return 'Falli guadagnati dal giocatore'
  if (s.includes('committed')) return 'Falli commessi'
  if (s.includes('drawn')) return 'Falli subiti'
  return null
}

function passesDisplay(p: string): string | null {
  const s = p.toLowerCase()
  if (s.includes('possession')) return 'Possesso palla'
  if (s.includes('key') && s.includes('pass')) return 'Passaggi chiave'
  if (s.includes('accuracy') || s.includes('accurate')) return 'Precisione passaggi'
  if (s.includes('passes')) return s.includes('total') ? 'Passaggi totali' : 'Passaggi'
  return null
}

function gkDisplay(p: string): string | null {
  const s = p.toLowerCase()
  if (s.includes('saves')) return 'Parate portiere'
  if (s.includes('clean')) return 'Clean sheet'
  if (s.includes('conceded') && s.includes('goal')) return 'Goal subiti dal portiere'
  return null
}

function lineupDisplay(p: string): string | null {
  const s = p.toLowerCase()
  if (s.includes('formation')) return 'Modulo tattico'
  if (s.includes('startxi')) return 'Titolare (formazione)'
  if (s.includes('substitute')) return 'Panchina'
  if (s.includes('minutes')) return 'Minuti giocati'
  if (s.includes('position')) return 'Ruolo giocatore'
  if (s.includes('rating')) return 'Rating giocatore'
  if (s.includes('captain')) return 'Capitano'
  return null
}

function injuryDisplay(p: string): string | null {
  const s = p.toLowerCase()
  if (s.includes('player') && s.includes('name')) return 'Giocatore infortunato'
  if (s.includes('type')) return 'Tipo infortunio'
  if (s.includes('reason')) return 'Motivo indisponibilità'
  if (s.includes('fixture.date')) return 'Data partita (contesto infortunio)'
  return null
}

function standingsDisplay(p: string): string | null {
  const s = p.toLowerCase()
  if (s.includes('rank')) return 'Posizione in classifica'
  if (s.includes('points')) return 'Punti'
  if (s.includes('form')) return 'Forma recente in classifica'
  if (s.includes('wins')) return 'Vittorie'
  if (s.includes('draws')) return 'Pareggi'
  if (s.includes('lose') || s.includes('defeats')) return 'Sconfitte'
  if (s.includes('played')) return 'Partite giocate'
  if (s.includes('goalsdiff') || s.includes('goals diff')) return 'Differenza reti'
  return null
}

function contestoDisplay(p: string): string | null {
  const s = p.toLowerCase()
  if (s.includes('fixture.date')) return 'Data partita'
  if (s.includes('fixture.timestamp')) return 'Timestamp partita'
  if (s.includes('fixture.status')) return 'Stato partita'
  if (s.includes('round')) return 'Giornata / round'
  return null
}

export function getCatalogFieldDisplayName(field: ModelRelevantField): string {
  const p = normPath(field)
  const b = blob(field)
  const ni = (field.name_it || '').trim()

  const goalTitle = goalOverUnderDisplayName(field)
  if (goalTitle) return goalTitle

  const tiriPortaTitle = tiriInPortaDisplayName(field)
  if (tiriPortaTitle) return tiriPortaTitle

  const shotsTiriTitle = shotsTiriDisplayName(field)
  if (shotsTiriTitle) return shotsTiriTitle

  const cornerTitle = cornerDisplayName(field)
  if (cornerTitle) return cornerTitle

  const cartelliniTitle = cartelliniDisplayName(field)
  if (cartelliniTitle) return cartelliniTitle

  const pen = penaltyDisplayName(field)
  if (pen) return pen

  const gou = goalsUnderOverDisplay(p)
  if (gou) return gou

  const sc = scoreDisplay(p)
  if (sc) return sc

  const gsc = goalsScorePathDisplay(p)
  if (gsc) return gsc

  const grp = getCatalogFieldGroup(field)

  if (grp === 'quote_bookmaker') {
    if (/\bover\b.*\bunder\b|\bunder\b.*\bover\b/.test(p) || (p.includes('over') && p.includes('under'))) {
      if (p.includes('goal') || b.includes('goal')) return 'Quota Over/Under goal'
      return 'Over/Under bookmaker — mercato da leggere nei dettagli'
    }
    return ni && !GENERIC_BAD.test(ni) ? ni : 'Quota bookmaker'
  }

  if (grp === 'tiri') {
    const sd = shotsDisplay(p, ni)
    if (sd) return sd
  }

  if (grp === 'falli') {
    const fd = foulsDisplay(p)
    if (fd) return fd
  }

  if (grp === 'passaggi_possesso') {
    const pd = passesDisplay(p)
    if (pd) return pd
  }

  if (grp === 'parate_portieri') {
    const gd = gkDisplay(p)
    if (gd) return gd
  }

  if (grp === 'formazioni_giocatori') {
    const ld = lineupDisplay(p)
    if (ld) return ld
  }

  if (grp === 'infortuni') {
    const id = injuryDisplay(p)
    if (id) return id
  }

  if (grp === 'classifica_motivazione') {
    const sd = standingsDisplay(p)
    if (sd) return sd
  }

  if (grp === 'contesto_tecnico') {
    const cd = contestoDisplay(p)
    if (cd) return cd
  }

  if (GENERIC_BAD.test(ni) || GENERIC_BAD.test(field.technical_name || '')) {
    return `${getSemanticGroupTitle(grp)}: ${field.json_path || field.key}`
  }

  return ni || field.json_path || field.key
}

export function getCatalogFieldDescription(field: ModelRelevantField): string {
  const goalDesc = goalOverUnderDescription(field)
  if (goalDesc) return goalDesc

  const tiriPortaDesc = tiriInPortaDescription(field)
  if (tiriPortaDesc) return tiriPortaDesc

  const shotsDesc = shotsTiriDescription(field)
  if (shotsDesc) return shotsDesc

  const cornerDesc = cornerDescription(field)
  if (cornerDesc) return cornerDesc

  const cartelliniDesc = cartelliniDescription(field)
  if (cartelliniDesc) return cartelliniDesc

  const reason = (field.reason || '').trim()
  if (reason.length >= 24) return reason

  const grp = getSemanticGroupTitle(getCatalogFieldGroup(field))
  const extra = `Variabile nel gruppo «${grp}».`
  if (!reason) return `${extra} Path: ${field.json_path}.`
  return `${reason} ${extra}`
}

export function getCatalogFieldTooltip(field: ModelRelevantField): string {
  const g = getCatalogFieldGroup(field)
  if (g === 'quote_bookmaker') {
    return 'Per quote e Over/Under verifica mercato, linea e bookmaker nei dettagli tecnici e nei mercati consigliati.'
  }
  if (g === 'contesto_tecnico') {
    return 'Dato di contesto (date, round, stato) utile per ordinamento, rest days e anti-leakage; di solito non è una feature diretta.'
  }
  if (g === 'tiri_in_porta') {
    return 'Solo tiri nello specchio (SOT): squadra, giocatore, stagione, concessi e quote dedicate; non include volume tiri totali o fuori.'
  }
  if (g === 'corner') {
    return 'Solo calci d’angolo: statistiche battuti/concessi e mercati bookmaker chiaramente corner; non include tiri, goal o cartellini.'
  }
  if (g === 'cartellini') {
    return 'Solo disciplina: gialli/rossi squadra e giocatore, classifiche top cards e quote cartellini chiare; non include falli, tiri o corner.'
  }
  return `Gruppo: ${getSemanticGroupTitle(g)}.`
}

export function semanticGroupOptionsForFilter(): { id: SemanticGroupId; title: string }[] {
  return SEMANTIC_GROUP_ORDER.map((id) => ({ id, title: getSemanticGroupTitle(id) }))
}

export type SemanticGroupSection = {
  id: SemanticGroupId
  title: string
  parameters: ModelRelevantField[]
  /** Sotto-gruppi UI (sezione Goal). */
  subsections?: GoalSubsection[]
  /** Testo esplicativo sotto il titolo sezione (es. Tiri volume). */
  sectionSubtitle?: string
  /** Altre sezioni non ancora riviste con le nuove regole bloccate. */
  sectionReviewPending?: boolean
}

/** Raggruppa e ordina campi per gruppo statistico (accordion UI). */
export function groupFieldsBySemanticOrder(fields: ModelRelevantField[]): SemanticGroupSection[] {
  const map = new Map<SemanticGroupId, ModelRelevantField[]>()
  for (const id of SEMANTIC_GROUP_ORDER) map.set(id, [])
  for (const f of fields) {
    const g = getCatalogFieldGroup(f)
    map.get(g)!.push(f)
  }
  const out: SemanticGroupSection[] = []
  for (const id of SEMANTIC_GROUP_ORDER) {
    const raw = map.get(id) ?? []
    if (id === 'goal_over_under') {
      const { allOrdered, subsections } = organizeGoalOverUnderSection(raw)
      if (allOrdered.length === 0) continue
      out.push({
        id,
        title: getSemanticGroupTitle(id),
        parameters: allOrdered,
        subsections,
        sectionReviewPending: false,
      })
      continue
    }
    if (id === 'tiri_in_porta') {
      const organized = organizeTiriInPortaSection(raw)
      const hasOrganized = organized.allOrdered.length > 0
      const parameters = hasOrganized
        ? organized.allOrdered
        : [...raw].sort((a, b) =>
            getCatalogFieldDisplayName(a).localeCompare(getCatalogFieldDisplayName(b), 'it', { sensitivity: 'base' }),
          )
      if (parameters.length === 0) continue
      out.push({
        id,
        title: getSemanticGroupTitle(id),
        parameters,
        subsections: hasOrganized ? organized.subsections : undefined,
        sectionSubtitle: TIRI_IN_PORTA_SECTION_SUBTITLE,
        sectionReviewPending: false,
      })
      continue
    }
    if (id === 'tiri') {
      const organized = organizeShotsTiriSection(raw)
      const hasOrganized = organized.allOrdered.length > 0
      const parameters = hasOrganized
        ? organized.allOrdered
        : [...raw].sort((a, b) =>
            getCatalogFieldDisplayName(a).localeCompare(getCatalogFieldDisplayName(b), 'it', { sensitivity: 'base' }),
          )
      if (parameters.length === 0) continue
      out.push({
        id,
        title: getSemanticGroupTitle(id),
        parameters,
        subsections: hasOrganized ? organized.subsections : undefined,
        sectionSubtitle: SHOTS_TIRI_SECTION_SUBTITLE,
        sectionReviewPending: false,
      })
      continue
    }
    if (id === 'corner') {
      const organized = organizeCornerSection(raw)
      const hasOrganized = organized.allOrdered.length > 0
      const parameters = hasOrganized
        ? organized.allOrdered
        : [...raw].sort((a, b) =>
            getCatalogFieldDisplayName(a).localeCompare(getCatalogFieldDisplayName(b), 'it', { sensitivity: 'base' }),
          )
      if (parameters.length === 0) continue
      out.push({
        id,
        title: getSemanticGroupTitle(id),
        parameters,
        subsections: hasOrganized ? organized.subsections : undefined,
        sectionSubtitle: CORNER_SECTION_SUBTITLE,
        sectionReviewPending: false,
      })
      continue
    }
    if (id === 'cartellini') {
      const organized = organizeCartelliniSection(raw)
      const hasOrganized = organized.allOrdered.length > 0
      const parameters = hasOrganized
        ? organized.allOrdered
        : [...raw].sort((a, b) =>
            getCatalogFieldDisplayName(a).localeCompare(getCatalogFieldDisplayName(b), 'it', { sensitivity: 'base' }),
          )
      if (parameters.length === 0) continue
      out.push({
        id,
        title: getSemanticGroupTitle(id),
        parameters,
        subsections: hasOrganized ? organized.subsections : undefined,
        sectionSubtitle: CARTELLINI_SECTION_SUBTITLE,
        sectionReviewPending: false,
      })
      continue
    }
    const parameters = [...raw].sort((a, b) =>
      getCatalogFieldDisplayName(a).localeCompare(getCatalogFieldDisplayName(b), 'it', { sensitivity: 'base' }),
    )
    if (parameters.length === 0) continue
    out.push({
      id,
      title: getSemanticGroupTitle(id),
      parameters,
      sectionReviewPending: true,
    })
  }
  return out
}

export function countV04Stats(parameters: ModelRelevantField[]): {
  total: number
  usedV04: number
  future: number
} {
  let usedV04 = 0
  let future = 0
  for (const p of parameters) {
    if (p.model_v04_status === 'used_v04') usedV04++
    if (p.model_v04_status === 'not_used_v04' && p.classification === 'TENERE_FUTURO_MODELLO') future++
  }
  return { total: parameters.length, usedV04, future }
}
