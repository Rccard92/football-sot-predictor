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
