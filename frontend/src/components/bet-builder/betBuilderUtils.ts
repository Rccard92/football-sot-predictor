import type {
  BetBuilderMarketKey,
  BetBuilderOpportunity,
  BetBuilderOrigin,
} from '../../lib/cecchinoBetBuilderApi'

export const BET_BUILDER_PAGE_SIZE = 12

export const BET_BUILDER_POLL_IDLE_MS = 60_000
export const BET_BUILDER_POLL_RUNNING_MS = 2_500

export type BetBuilderMarketFilter = 'all' | BetBuilderMarketKey
export type BetBuilderOriginFilter = 'all' | BetBuilderOrigin
export type BetBuilderSortKey =
  | 'purchasability_desc'
  | 'signals_desc'
  | 'edge_desc'
  | 'kickoff_asc'

export type BetBuilderFilterState = {
  market: BetBuilderMarketFilter
  origin: BetBuilderOriginFilter
  country: string
  league: string
  search: string
  minPurchasability: number | null
  sort: BetBuilderSortKey
}

export const DEFAULT_BET_BUILDER_FILTERS: BetBuilderFilterState = {
  market: 'all',
  origin: 'all',
  country: '',
  league: '',
  search: '',
  minPurchasability: null,
  sort: 'purchasability_desc',
}

export type BetBuilderFixtureOriginCounts = {
  total: number
  price_only: number
  signals_only: number
  price_and_signals: number
}

export type BetBuilderFixtureGroup = {
  todayFixtureId: number
  fixture: BetBuilderOpportunity['fixture']
  opportunities: BetBuilderOpportunity[]
  counts: BetBuilderFixtureOriginCounts
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

const ORIGIN_RANK: Record<BetBuilderOrigin, number> = {
  price_and_signals: 0,
  signals: 1,
  price: 2,
}

export function isIsoDate(value: string | null | undefined): value is string {
  if (!value || !ISO_DATE_RE.test(value)) return false
  const d = new Date(`${value}T12:00:00Z`)
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value
}

export function shiftIsoDate(dateIso: string, deltaDays: number): string {
  const d = new Date(`${dateIso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + deltaDays)
  return d.toISOString().slice(0, 10)
}

export function formatKickoffShort(kickoff: string | null | undefined): string {
  if (!kickoff) return '—'
  const d = new Date(kickoff)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('it-IT', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Rome',
  })
}

export function formatUpdatedAt(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('it-IT', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Rome',
  })
}

export function originBadgeLabel(origin: BetBuilderOrigin): string {
  if (origin === 'price') return 'QUOTA'
  if (origin === 'signals') return 'SEGNALI'
  return 'QUOTA + SEGNALI'
}

export function uniqueSorted(values: Array<string | null | undefined>): string[] {
  const set = new Set<string>()
  for (const v of values) {
    const t = (v ?? '').trim()
    if (t) set.add(t)
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b, 'it'))
}

function matchesSearch(op: BetBuilderOpportunity, search: string): boolean {
  const q = search.trim().toLowerCase()
  if (!q) return true
  const home = (op.fixture.home.name ?? '').toLowerCase()
  const away = (op.fixture.away.name ?? '').toLowerCase()
  return home.includes(q) || away.includes(q)
}

export function filterOpportunities(
  opportunities: BetBuilderOpportunity[],
  filters: BetBuilderFilterState,
): BetBuilderOpportunity[] {
  return opportunities.filter((op) => {
    if (filters.market !== 'all' && op.market.market_key !== filters.market) return false
    if (filters.origin !== 'all' && op.origin !== filters.origin) return false
    if (filters.country && (op.fixture.country ?? '') !== filters.country) return false
    if (filters.league && (op.fixture.league ?? '') !== filters.league) return false
    if (!matchesSearch(op, filters.search)) return false
    if (filters.minPurchasability != null) {
      const score = op.purchasability_v31.score
      if (score == null || score < filters.minPurchasability) return false
    }
    return true
  })
}

function cmpNullableNumberDesc(a: number | null | undefined, b: number | null | undefined): number {
  const aNull = a == null || Number.isNaN(a)
  const bNull = b == null || Number.isNaN(b)
  if (aNull && bNull) return 0
  if (aNull) return 1
  if (bNull) return -1
  return (b as number) - (a as number)
}

function cmpKickoffAsc(a: string | null | undefined, b: string | null | undefined): number {
  const aMissing = !a
  const bMissing = !b
  if (aMissing && bMissing) return 0
  if (aMissing) return 1
  if (bMissing) return -1
  return a!.localeCompare(b!)
}

/** Sort legacy flat list (usato da test regressione / compatibilità). */
export function sortOpportunities(
  opportunities: BetBuilderOpportunity[],
  sort: BetBuilderSortKey,
): BetBuilderOpportunity[] {
  const copy = [...opportunities]
  copy.sort((a, b) => {
    let primary: number
    if (sort === 'purchasability_desc') {
      primary = cmpNullableNumberDesc(a.purchasability_v31.score, b.purchasability_v31.score)
    } else if (sort === 'signals_desc') {
      primary = cmpNullableNumberDesc(a.signals.yes_count, b.signals.yes_count)
    } else if (sort === 'edge_desc') {
      primary = cmpNullableNumberDesc(a.price_value.edge_pct, b.price_value.edge_pct)
    } else {
      primary = cmpKickoffAsc(a.fixture.kickoff, b.fixture.kickoff)
    }
    if (primary !== 0) return primary
    return a.opportunity_key.localeCompare(b.opportunity_key)
  })
  return copy
}

export function filterAndSortOpportunities(
  opportunities: BetBuilderOpportunity[],
  filters: BetBuilderFilterState,
): BetBuilderOpportunity[] {
  return sortOpportunities(filterOpportunities(opportunities, filters), filters.sort)
}

/** Ordinamento deterministico delle opportunity dentro una fixture (§11). */
export function sortOpportunitiesWithinFixture(
  opportunities: BetBuilderOpportunity[],
): BetBuilderOpportunity[] {
  const copy = [...opportunities]
  copy.sort((a, b) => {
    const byScore = cmpNullableNumberDesc(
      a.purchasability_v31.score,
      b.purchasability_v31.score,
    )
    if (byScore !== 0) return byScore
    const byOrigin = ORIGIN_RANK[a.origin] - ORIGIN_RANK[b.origin]
    if (byOrigin !== 0) return byOrigin
    const byYes = cmpNullableNumberDesc(a.signals.yes_count, b.signals.yes_count)
    if (byYes !== 0) return byYes
    const byEdge = cmpNullableNumberDesc(a.price_value.edge_pct, b.price_value.edge_pct)
    if (byEdge !== 0) return byEdge
    return a.opportunity_key.localeCompare(b.opportunity_key)
  })
  return copy
}

export function fixtureOpportunityCounts(
  opportunities: BetBuilderOpportunity[],
): BetBuilderFixtureOriginCounts {
  let price_only = 0
  let signals_only = 0
  let price_and_signals = 0
  for (const op of opportunities) {
    if (op.origin === 'price') price_only += 1
    else if (op.origin === 'signals') signals_only += 1
    else price_and_signals += 1
  }
  return {
    total: opportunities.length,
    price_only,
    signals_only,
    price_and_signals,
  }
}

export function groupOpportunitiesByFixture(
  opportunities: BetBuilderOpportunity[],
): BetBuilderFixtureGroup[] {
  const map = new Map<number, BetBuilderOpportunity[]>()
  const order: number[] = []
  for (const op of opportunities) {
    const id = op.fixture.today_fixture_id
    const existing = map.get(id)
    if (existing) {
      existing.push(op)
    } else {
      map.set(id, [op])
      order.push(id)
    }
  }
  return order.map((id) => {
    const ops = sortOpportunitiesWithinFixture(map.get(id) ?? [])
    const first = ops[0]
    return {
      todayFixtureId: id,
      fixture: first.fixture,
      opportunities: ops,
      counts: fixtureOpportunityCounts(ops),
    }
  })
}

function maxNullable(values: Array<number | null | undefined>): number | null {
  let best: number | null = null
  for (const v of values) {
    if (v == null || Number.isNaN(v)) continue
    if (best == null || v > best) best = v
  }
  return best
}

export function sortFixtureGroups(
  groups: BetBuilderFixtureGroup[],
  sort: BetBuilderSortKey,
): BetBuilderFixtureGroup[] {
  const copy = [...groups]
  copy.sort((a, b) => {
    let primary: number
    if (sort === 'purchasability_desc') {
      primary = cmpNullableNumberDesc(
        maxNullable(a.opportunities.map((o) => o.purchasability_v31.score)),
        maxNullable(b.opportunities.map((o) => o.purchasability_v31.score)),
      )
    } else if (sort === 'signals_desc') {
      primary = cmpNullableNumberDesc(
        maxNullable(a.opportunities.map((o) => o.signals.yes_count)),
        maxNullable(b.opportunities.map((o) => o.signals.yes_count)),
      )
    } else if (sort === 'edge_desc') {
      primary = cmpNullableNumberDesc(
        maxNullable(a.opportunities.map((o) => o.price_value.edge_pct)),
        maxNullable(b.opportunities.map((o) => o.price_value.edge_pct)),
      )
    } else {
      primary = cmpKickoffAsc(a.fixture.kickoff, b.fixture.kickoff)
    }
    if (primary !== 0) return primary
    return a.todayFixtureId - b.todayFixtureId
  })
  return copy
}

export function buildBetBuilderFixtureGroups(
  opportunities: BetBuilderOpportunity[],
  filters: BetBuilderFilterState,
): BetBuilderFixtureGroup[] {
  const filtered = filterOpportunities(opportunities, filters)
  const grouped = groupOpportunitiesByFixture(filtered)
  return sortFixtureGroups(grouped, filters.sort)
}

export function countUniqueFixtures(opportunities: BetBuilderOpportunity[]): number {
  const ids = new Set<number>()
  for (const op of opportunities) {
    ids.add(op.fixture.today_fixture_id)
  }
  return ids.size
}

export function countFilteredOpportunities(groups: BetBuilderFixtureGroup[]): number {
  return groups.reduce((sum, g) => sum + g.opportunities.length, 0)
}

export function sliceProgressive<T>(items: T[], limit: number): T[] {
  return items.slice(0, Math.max(0, limit))
}

export function nextVisibleLimit(current: number, total: number, step = BET_BUILDER_PAGE_SIZE): number {
  return Math.min(total, current + step)
}

export function isScanRunning(status: string | null | undefined): boolean {
  return status === 'running' || status === 'queued'
}

export function resolveLastUpdatedIso(
  freshness: {
    max_fixture_updated_at?: string | null
    max_purchasability_v31_generated_at?: string | null
  } | null | undefined,
  sourceGeneratedFrom?: {
    max_fixture_updated_at?: string | null
    latest_scan_job?: { finished_at?: string | null; updated_at?: string | null } | null
  } | null,
): string | null {
  const candidates = [
    freshness?.max_fixture_updated_at,
    freshness?.max_purchasability_v31_generated_at,
    sourceGeneratedFrom?.max_fixture_updated_at,
    sourceGeneratedFrom?.latest_scan_job?.finished_at,
    sourceGeneratedFrom?.latest_scan_job?.updated_at,
  ].filter((v): v is string => Boolean(v))
  if (candidates.length === 0) return null
  return candidates.sort().at(-1) ?? null
}
