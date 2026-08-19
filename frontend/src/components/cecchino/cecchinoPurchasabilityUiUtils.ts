/** Helper UI Acquistabilità — nessuna logica di business. */

import type { CecchinoPurchasabilityV31Item } from '../../lib/cecchinoTodayApi'

/** Ordine canonico allineato a backend PANEL_MARKET_KEYS. */
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

export const V31_REASON_CODE_LABELS: Record<string, string> = {
  book_quote_unavailable: 'Quota Book non disponibile',
  derived_quote_not_executable: 'Quota derivata non eseguibile',
  cecchino_quote_unavailable: 'Quota Cecchino assente',
  positive_edge: 'Edge positivo',
  failed_non_positive_edge: 'Edge non positivo',
  rating_below_purchase_scope: 'Rating sotto soglia acquisto',
  insufficient_history: 'Storico insufficiente',
  historical_sample_insufficient: 'Campione storico insufficiente',
  family_ambiguity_penalty: 'Penalità ambiguità famiglia',
  probability_risk_penalty: 'Penalità rischio probabilistico',
  complement_pressure: 'Pressione opposta elevata',
  fair_book_unverified: 'Fair Book non verificato',
}

export function getPurchasabilityScore(item: CecchinoPurchasabilityV31Item): number | null {
  const raw = item.score_v31 ?? item.score
  if (raw == null || Number.isNaN(Number(raw))) return null
  return Number(raw)
}

export function getPurchasabilityClassLabel(item: CecchinoPurchasabilityV31Item): string | null {
  const cls = item.class_v31 ?? item.class
  return cls != null ? String(cls) : null
}

export function getMarketDisplayLabel(item: CecchinoPurchasabilityV31Item): string {
  return item.market_label ?? item.label ?? item.market_key
}

export type PurchasabilityVersionMeta = {
  candidateName?: string | null
  candidateVersion?: string | null
  formulaVersion?: string | null
}

const CANDIDATE_NAME_LABELS: Record<string, string> = {
  v31_shadow: 'V3.1 SHADOW',
}

/** Label friendly per il pannello Today (es. "V3.1 SHADOW"). */
export function getPurchasabilityFriendlyVersionLabel(meta: PurchasabilityVersionMeta): string {
  const name = meta.candidateName?.trim()
  if (name && CANDIDATE_NAME_LABELS[name]) return CANDIDATE_NAME_LABELS[name]
  if (meta.formulaVersion?.includes('purchasability_v31')) return 'V3.1 SHADOW'
  return 'V3.1 SHADOW'
}

/** Suffisso breve formula (es. "empirical_v2") da formula_version snapshot. */
export function getPurchasabilityFormulaShortLabel(
  formulaVersion?: string | null,
): string | null {
  const v = formulaVersion?.trim()
  if (!v) return null
  const empirical = v.match(/empirical_v\d+$/)
  if (empirical) return empirical[0]
  const shadow = v.match(/shadow_v\d+$/)
  if (shadow) return shadow[0]
  return null
}

export function isActivePurchasabilityMarket(item: CecchinoPurchasabilityV31Item): boolean {
  return (
    (item.status === 'score' || item.status === 'score_provisional') &&
    getPurchasabilityScore(item) != null
  )
}

export function listActivePurchasabilityMarkets(
  itemsByMarket: Record<string, CecchinoPurchasabilityV31Item>,
): CecchinoPurchasabilityV31Item[] {
  const active = Object.values(itemsByMarket).filter(isActivePurchasabilityMarket)
  return active.sort((a, b) => {
    const sa = getPurchasabilityScore(a) ?? -1
    const sb = getPurchasabilityScore(b) ?? -1
    if (sb !== sa) return sb - sa
    const oa = PANEL_MARKET_ORDER.get(a.market_key) ?? 999
    const ob = PANEL_MARKET_ORDER.get(b.market_key) ?? 999
    return oa - ob
  })
}

export function defaultSelectedMarketKey(
  itemsByMarket: Record<string, CecchinoPurchasabilityV31Item>,
): string | null {
  const sorted = listActivePurchasabilityMarkets(itemsByMarket)
  return sorted[0]?.market_key ?? null
}

function humanizeReasonCode(code: string): string {
  return V31_REASON_CODE_LABELS[code] ?? code.replace(/_/g, ' ')
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

/** Max 2–4 motivazioni da output V3.1 reali. */
export function buildPurchasabilityReasonBullets(
  item: CecchinoPurchasabilityV31Item,
  max = 4,
): string[] {
  const bullets: string[] = []
  const push = (s: string) => {
    if (bullets.length < max && s && !bullets.includes(s)) bullets.push(s)
  }

  const inp = asRecord(item.input)
  if (inp?.quota_book != null) {
    push(`Quota Book ${Number(inp.quota_book).toFixed(2)}`)
  }
  if (inp?.edge_pct != null) {
    const edge = Number(inp.edge_pct)
    push(`Edge ${edge > 0 ? '+' : ''}${edge.toFixed(2)}%`)
  }
  if (inp?.probability_advantage_pp != null) {
    const pp = Number(inp.probability_advantage_pp)
    push(`Vantaggio probabilistico ${pp > 0 ? '+' : ''}${pp.toFixed(1)} pp`)
  }
  const complement = inp?.complement_fair_probability
  if (complement != null) {
    push(`Pressione opposta ${(Number(complement) * 100).toFixed(1)}%`)
  }

  const theoretical = asRecord(item.theoretical)
  const penalties = theoretical?.penalties as { penalties_applied?: Array<{ label?: string }> } | undefined
  for (const p of penalties?.penalties_applied ?? []) {
    if (p.label) push(p.label)
  }
  if (theoretical?.family_ambiguity_status === 'ambiguous') {
    push('Ambiguità nella famiglia di mercato')
  }

  const historical = asRecord(item.historical)
  if (historical?.historical_multiplier != null) {
    push(`Moltiplicatore storico ${Number(historical.historical_multiplier).toFixed(2)}`)
  }
  const sample =
    historical?.selected_sample_size ?? historical?.sample_size ?? item.historical?.sample_size
  if (sample != null) {
    push(`Campione storico ${sample}`)
  }

  for (const code of item.reason_codes ?? []) {
    if (typeof code === 'string') push(humanizeReasonCode(code))
  }
  for (const code of (item as Record<string, unknown>).gate_reason_codes as string[] | undefined ?? []) {
    push(humanizeReasonCode(code))
  }
  for (const code of (item as Record<string, unknown>).historical_reason_codes as string[] | undefined ?? []) {
    push(humanizeReasonCode(code))
  }

  return bullets.slice(0, max)
}

export function purchasabilityBadgeClass(classLabel: string | null | undefined): string {
  const base = 'inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums'
  switch (classLabel?.replace(' provvisoria', '')) {
    case 'Molto Alta':
    case 'Alta':
      return `${base} bg-emerald-600 text-white`
    case 'Media':
      return `${base} bg-sky-600 text-white`
    case 'Bassa':
      return `${base} bg-orange-500/90 text-white`
    case 'Molto Bassa':
      return `${base} bg-rose-700/80 text-white`
    default:
      return `${base} bg-slate-600 text-slate-100`
  }
}
