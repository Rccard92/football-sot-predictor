import type { V4MarketRow, V4Side } from '../../lib/cecchinoV4Api'

export type StatKeyParts = {
  stat: string
  side: V4Side
  direction: 'over' | 'under'
  line: string
}

/** `STAT:sot:away:over:6.5` → parti; null per i mercati classici. */
export function parseStatKey(key: string): StatKeyParts | null {
  const parts = key.split(':')
  if (parts.length !== 5 || parts[0] !== 'STAT') return null
  const [, stat, side, direction, line] = parts
  if (side !== 'home' && side !== 'away' && side !== 'total') return null
  if (direction !== 'over' && direction !== 'under') return null
  return { stat, side, direction, line }
}

export function statGroupKey(parts: StatKeyParts): string {
  return `${parts.stat}:${parts.side}`
}

export type StatGroup = {
  key: string
  stat: string
  side: V4Side
  lines: string[]
  /** riga over per linea */
  over: Record<string, V4MarketRow>
  /** riga under per linea, se il backend la manda */
  under: Record<string, V4MarketRow>
  bestProfit: number | null
}

export type SplitMarkets = {
  classic: V4MarketRow[]
  groups: StatGroup[]
}

function maxProfit(rows: V4MarketRow[]): number | null {
  let best: number | null = null
  for (const r of rows) {
    if (r.expected_profit == null) continue
    if (best == null || r.expected_profit > best) best = r.expected_profit
  }
  return best
}

/** Separa mercati classici e gruppi statistica/lato con l'elenco ordinato delle linee. */
export function splitMarkets(markets: V4MarketRow[]): SplitMarkets {
  const classic: V4MarketRow[] = []
  const groupMap = new Map<string, StatGroup>()
  for (const row of markets) {
    const parts = parseStatKey(row.market_key)
    if (!parts) {
      classic.push(row)
      continue
    }
    const gk = statGroupKey(parts)
    let g = groupMap.get(gk)
    if (!g) {
      g = { key: gk, stat: parts.stat, side: parts.side, lines: [], over: {}, under: {}, bestProfit: null }
      groupMap.set(gk, g)
    }
    if (!g.lines.includes(parts.line)) g.lines.push(parts.line)
    if (parts.direction === 'over') g.over[parts.line] = row
    else g.under[parts.line] = row
  }
  const groups = [...groupMap.values()].map((g) => {
    g.lines.sort((a, b) => Number(a) - Number(b))
    g.bestProfit = maxProfit([...Object.values(g.over), ...Object.values(g.under)])
    return g
  })
  return { classic, groups }
}

export function compareByProfitDesc(a: number | null, b: number | null): number {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  return b - a
}

/** Under derivato quando il backend manda solo l'over: p = 1 − over, nessuna quota. */
export function deriveUnderRow(over: V4MarketRow, label: string): V4MarketRow {
  const verdict = over.verdict === 'solo_descrittivo' ? 'solo_descrittivo' : 'non_quotato'
  return {
    market_key: over.market_key.replace(':over:', ':under:'),
    family: over.family,
    label,
    p: 1 - over.p,
    lo: 1 - over.hi,
    hi: 1 - over.lo,
    p_prudent: 1 - over.hi,
    quota_bet365: null,
    quota_betfair: null,
    quota_used: null,
    bookmaker_used: null,
    expected_profit: null,
    verdict,
    verdict_label: verdict === 'solo_descrittivo' ? 'Solo descrittivo' : 'Non quotato',
  }
}

/** Linea di partenza del selettore: quella della giocata migliore se nel gruppo, altrimenti la centrale. */
export function defaultLine(group: StatGroup, bestKey: string | null): string {
  if (bestKey) {
    const parts = parseStatKey(bestKey)
    if (parts && statGroupKey(parts) === group.key && group.lines.includes(parts.line)) return parts.line
  }
  return group.lines[Math.floor((group.lines.length - 1) / 2)] ?? ''
}
