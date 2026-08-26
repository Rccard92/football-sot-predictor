/** Helper UI Indice di Acquistabilità V3.6 (= Structural V2). Nessuna dipendenza V35 UI. */

import type { V36Item } from '../../lib/cecchinoTodayApi'
import {
  PANEL_MARKET_KEYS,
  PANEL_MARKET_ORDER,
} from './cecchinoPurchasabilityMarketKeys'

export { PANEL_MARKET_KEYS }

export const V36_STRUCTURAL_BLOCK_LABELS: Record<string, string> = {
  same_family_opposition: 'Opposizione stessa famiglia',
  side_cover: 'Copertura laterale',
  goal_ladder: 'Scala Goal',
}

/** Badge stile da class label persistita (mai ricalcolata). */
export function v36BadgeClass(classLabel: string | null | undefined): string {
  const base = 'inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-semibold ring-1'
  switch (classLabel) {
    case 'Eccezionale':
    case 'Molto Alta':
      return `${base} bg-emerald-50 text-emerald-900 ring-emerald-200`
    case 'Alta':
      return `${base} bg-lime-50 text-lime-900 ring-lime-200`
    case 'Media':
      return `${base} bg-amber-50 text-amber-900 ring-amber-200`
    case 'Bassa':
      return `${base} bg-orange-50 text-orange-900 ring-orange-200`
    case 'Molto Bassa':
      return `${base} bg-red-50 text-red-900 ring-red-200`
    default:
      return `${base} bg-slate-50 text-slate-700 ring-slate-200`
  }
}

export type V36HumanExplanation = {
  valore: string
  affidabilita: string
  struttura: string
  qualita: string
  conclusione: string
}

function bandLabel(score: number | null | undefined): 'basso' | 'medio' | 'alto' | 'nd' {
  if (score == null || Number.isNaN(Number(score))) return 'nd'
  const n = Number(score)
  if (n < 45) return 'basso'
  if (n < 65) return 'medio'
  return 'alto'
}

/**
 * Spiegazione umana deterministica da soli campi V3.6 esistenti.
 * Non predice esiti; descrive il punteggio (valore matematico, struttura, qualità dati).
 */
export function buildV36HumanExplanation(item: V36Item): V36HumanExplanation {
  const v = item.components?.executable_value?.score
  const d = item.components?.market_disagreement?.score
  const r = item.components?.base_rate_reliability?.score
  const s =
    item.components?.structural_coherence?.score ??
    item.components?.structural_coherence?.S
  const q = item.components?.information_quality?.score
  const sUnavailable =
    item.components?.structural_coherence?.structural_status === 'unavailable' ||
    s == null ||
    item.structural_missing_penalty_applied === true

  const vBand = bandLabel(v)
  const dBand = bandLabel(d)
  const rBand = bandLabel(r)
  const qBand = bandLabel(q)
  const finalScore = getV36Score(item)
  const classLabel = item.class?.trim() || null

  let valore: string
  if (vBand === 'nd' && dBand === 'nd') {
    valore = 'Valore matematico non valutabile con i dati disponibili.'
  } else if (vBand === 'alto' || dBand === 'alto') {
    valore =
      'Il valore matematico alla quota eseguibile e la divergenza rispetto al book risultano di supporto al punteggio.'
  } else if (vBand === 'basso' && dBand === 'basso') {
    valore =
      'Il valore matematico e la divergenza rispetto al book risultano deboli rispetto a questo mercato.'
  } else {
    valore =
      'Il valore matematico e la divergenza rispetto al book risultano in fascia intermedia.'
  }

  let affidabilita: string
  if (rBand === 'nd') {
    affidabilita = 'Indice base-rate non disponibile per questo mercato.'
  } else if (rBand === 'alto') {
    affidabilita =
      'L’indice base-rate indica una base probabilistica condivisa relativamente solida.'
  } else if (rBand === 'basso') {
    affidabilita =
      'L’indice base-rate indica una base probabilistica condivisa relativamente debole.'
  } else {
    affidabilita =
      'L’indice base-rate indica una base probabilistica condivisa in fascia intermedia.'
  }

  let struttura: string
  if (sUnavailable) {
    struttura =
      'Supporto strutturale insufficiente: applicata penalizzazione strutturale.'
  } else {
    const sBand = bandLabel(s)
    if (sBand === 'alto') {
      struttura =
        'La coerenza con i mercati correlati/opposti fornisce un supporto strutturale solido.'
    } else if (sBand === 'basso') {
      struttura =
        'La coerenza con i mercati correlati/opposti risulta debole (poco supporto strutturale).'
    } else {
      struttura =
        'La coerenza con i mercati correlati/opposti risulta in fascia intermedia.'
    }
  }

  const qComp = item.components?.information_quality
  const hasPenalty =
    (qComp?.overround_penalty ?? 0) > 0 ||
    (qComp?.fallback_penalty ?? 0) > 0 ||
    (qComp?.derived_fair_penalty ?? 0) > 0 ||
    (qComp?.extreme_divergence_penalty ?? 0) > 0

  let qualita: string
  if (qBand === 'nd') {
    qualita = 'Qualità dei dati non valutabile.'
  } else if (hasPenalty && qBand !== 'alto') {
    qualita =
      'La qualità dei dati presenta penalizzazioni (overround, fallback o divergenza) che riducono il punteggio.'
  } else if (qBand === 'alto') {
    qualita = 'La qualità dei dati disponibili risulta buona, con poche o nessuna penalizzazione.'
  } else if (qBand === 'basso') {
    qualita = 'La qualità dei dati disponibili risulta limitata o incompleta.'
  } else {
    qualita = 'La qualità dei dati disponibili risulta in fascia intermedia.'
  }

  const scorePart =
    finalScore != null ? `Punteggio ${Math.round(finalScore)}/100` : 'Punteggio non disponibile'
  const classPart = classLabel ? ` (${classLabel})` : ''
  const conclusione = `${scorePart}${classPart}: sintesi di valore matematico, indice base-rate, supporto strutturale e qualità dei dati — non una previsione sull’esito della partita.`

  return { valore, affidabilita, struttura, qualita, conclusione }
}

export function getV36MarketLabel(item: V36Item): string {
  return item.label ?? item.market_key
}

export function getV36Score(item: V36Item): number | null {
  if (item.score == null || Number.isNaN(Number(item.score))) return null
  return Number(item.score)
}

export function getV36RawScore(item: V36Item): number | null {
  if (item.raw_score == null || Number.isNaN(Number(item.raw_score))) return null
  return Number(item.raw_score)
}

export function formatV36FinalScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(Number(score))) return '— / 100'
  return `${Math.round(Number(score))} / 100`
}

export function formatV36ComponentScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(Number(score))) return 'N/D'
  return Number(score).toFixed(1)
}

export function formatV36OptionalNumber(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value == null || Number.isNaN(Number(value))) return 'N/D'
  return Number(value).toFixed(digits)
}

function sortByRawScoreDesc(a: V36Item, b: V36Item): number {
  const ra = getV36RawScore(a) ?? -Infinity
  const rb = getV36RawScore(b) ?? -Infinity
  if (rb !== ra) return rb - ra
  const oa = PANEL_MARKET_ORDER.get(a.market_key) ?? 999
  const ob = PANEL_MARKET_ORDER.get(b.market_key) ?? 999
  return oa - ob
}

export function listScoredV36Markets(
  itemsByMarket: Record<string, V36Item>,
): V36Item[] {
  return PANEL_MARKET_KEYS.map((key) => itemsByMarket[key])
    .filter((item): item is V36Item => !!item && item.status === 'score')
    .filter((item) => getV36RawScore(item) != null || getV36Score(item) != null)
    .sort(sortByRawScoreDesc)
}

export function listInactiveV36Markets(
  itemsByMarket: Record<string, V36Item>,
): V36Item[] {
  return PANEL_MARKET_KEYS.map((key) => itemsByMarket[key]).filter(
    (item): item is V36Item =>
      !!item && (item.status === 'gate_failed' || item.status === 'not_calculable'),
  )
}

export function defaultV36SelectedMarketKey(
  itemsByMarket: Record<string, V36Item>,
): string | null {
  return listScoredV36Markets(itemsByMarket)[0]?.market_key ?? null
}

export function countV36ScoreMarkets(
  itemsByMarket: Record<string, V36Item>,
): number {
  return listScoredV36Markets(itemsByMarket).length
}

export function structuralBlockLabel(blockType: string | null | undefined): string {
  if (!blockType) return 'Blocco strutturale'
  return V36_STRUCTURAL_BLOCK_LABELS[blockType] ?? blockType
}
