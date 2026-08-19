/** Helper UI Acquistabilità V3.5 — nessuna logica di business. */

import type {
  CecchinoPurchasabilityV35Candidate,
  CecchinoPurchasabilityV35CandidateKey,
  CecchinoPurchasabilityV35CandidateRegistryEntry,
  CecchinoPurchasabilityV35Item,
  CecchinoPurchasabilityV35Snapshot,
} from '../../lib/cecchinoTodayApi'

export const V35_CANDIDATE_KEYS: readonly CecchinoPurchasabilityV35CandidateKey[] = [
  'A',
  'B',
  'C',
  'D',
] as const

export const V35_CANDIDATE_LABELS: Record<CecchinoPurchasabilityV35CandidateKey, string> = {
  A: 'Balanced',
  B: 'Value Heavy',
  C: 'Structure Heavy',
  D: 'Quality Conservative',
}

export const PANEL_MARKET_KEYS: readonly string[] = [
  'HOME',
  'DRAW',
  'AWAY',
  'HOME_PT',
  'DRAW_PT',
  'AWAY_PT',
  'ONE_X',
  'X_TWO',
  'ONE_TWO',
  'OVER_1_5',
  'UNDER_1_5',
  'OVER_2_5',
  'UNDER_2_5',
  'OVER_3_5',
  'UNDER_3_5',
  'OVER_PT_0_5',
  'UNDER_PT_0_5',
  'OVER_PT_1_5',
  'UNDER_PT_1_5',
] as const

const PANEL_MARKET_ORDER = new Map(PANEL_MARKET_KEYS.map((k, i) => [k, i]))

export function isActiveV35Market(item: CecchinoPurchasabilityV35Item): boolean {
  if (item.status !== 'score') return false
  return getV35CandidateScore(item, 'A') != null || getV35CandidateScore(item, 'B') != null
}

export function getV35CandidateScore(
  item: CecchinoPurchasabilityV35Item,
  candidate: CecchinoPurchasabilityV35CandidateKey,
): number | null {
  const raw = item.candidates?.[candidate]?.score
  if (raw == null || Number.isNaN(Number(raw))) return null
  return Number(raw)
}

export function getV35CandidateRawScore(
  item: CecchinoPurchasabilityV35Item,
  candidate: CecchinoPurchasabilityV35CandidateKey,
): number | null {
  const raw = item.candidates?.[candidate]?.raw_score
  if (raw == null || Number.isNaN(Number(raw))) return null
  return Number(raw)
}

export function getV35CandidateClass(
  item: CecchinoPurchasabilityV35Item,
  candidate: CecchinoPurchasabilityV35CandidateKey,
): string | null {
  return item.candidates?.[candidate]?.class ?? null
}

export function getV35MarketLabel(item: CecchinoPurchasabilityV35Item): string {
  return item.label ?? item.market_key
}

export function listActiveV35Markets(
  itemsByMarket: Record<string, CecchinoPurchasabilityV35Item>,
  candidate: CecchinoPurchasabilityV35CandidateKey = 'A',
): CecchinoPurchasabilityV35Item[] {
  return PANEL_MARKET_KEYS.map((key) => itemsByMarket[key])
    .filter((item): item is CecchinoPurchasabilityV35Item => !!item && item.status === 'score')
    .filter((item) => getV35CandidateScore(item, candidate) != null)
    .sort((a, b) => {
      const sa = getV35CandidateScore(a, candidate) ?? -1
      const sb = getV35CandidateScore(b, candidate) ?? -1
      if (sb !== sa) return sb - sa
      const oa = PANEL_MARKET_ORDER.get(a.market_key) ?? 999
      const ob = PANEL_MARKET_ORDER.get(b.market_key) ?? 999
      return oa - ob
    })
}

export function defaultV35SelectedMarketKey(
  itemsByMarket: Record<string, CecchinoPurchasabilityV35Item>,
  candidate: CecchinoPurchasabilityV35CandidateKey = 'A',
): string | null {
  const active = listActiveV35Markets(itemsByMarket, candidate)
  return active[0]?.market_key ?? null
}

export function countV35ScoreMarkets(
  itemsByMarket: Record<string, CecchinoPurchasabilityV35Item>,
): number {
  return PANEL_MARKET_KEYS.filter((key) => {
    const item = itemsByMarket[key]
    return item?.status === 'score'
  }).length
}

export function resolveV35CandidateRegistry(
  snapshot: CecchinoPurchasabilityV35Snapshot | null | undefined,
): Partial<
  Record<CecchinoPurchasabilityV35CandidateKey, CecchinoPurchasabilityV35CandidateRegistryEntry>
> {
  return snapshot?.candidate_registry ?? snapshot?.frozen_config?.candidates ?? {}
}

export function formatV35CandidateWeightsSubtitle(
  entry: CecchinoPurchasabilityV35CandidateRegistryEntry | undefined,
): string | null {
  const weights = entry?.weights
  if (!weights) return null
  const parts = ['V', 'D', 'S', 'Q']
    .map((k) => {
      const w = weights[k]
      if (w == null) return null
      return `${Math.round(Number(w) * 100)}${k}`
    })
    .filter((p): p is string => p != null)
  return parts.length ? parts.join(' · ') : null
}

export function v35BadgeClass(classLabel: string | null | undefined): string {
  switch (classLabel) {
    case 'Molto Alta':
      return 'bg-emerald-100 text-emerald-900 ring-emerald-200'
    case 'Alta':
      return 'bg-green-100 text-green-900 ring-green-200'
    case 'Media':
      return 'bg-sky-100 text-sky-900 ring-sky-200'
    case 'Bassa':
      return 'bg-orange-100 text-orange-900 ring-orange-200'
    case 'Molto Bassa':
      return 'bg-red-100 text-red-900 ring-red-200'
    default:
      return 'bg-slate-100 text-slate-700 ring-slate-200'
  }
}

export function formatV35ComponentScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(Number(score))) return 'N/D'
  return Number(score).toFixed(1)
}

export function formatV35IntegerScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(Number(score))) return '—'
  return String(Math.round(Number(score)))
}

export function formatV35Percent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return 'N/D'
  return `${Math.round(Number(value) * 100)}%`
}

export function getV35CandidateFromItem(
  item: CecchinoPurchasabilityV35Item,
  candidate: CecchinoPurchasabilityV35CandidateKey,
): CecchinoPurchasabilityV35Candidate | undefined {
  return item.candidates?.[candidate]
}
