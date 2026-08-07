import { describe, expect, it } from 'vitest'
import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import {
  BET_BUILDER_PAGE_SIZE,
  DEFAULT_BET_BUILDER_FILTERS,
  buildBetBuilderFixtureGroups,
  countFilteredOpportunities,
  countUniqueFixtures,
  filterAndSortOpportunities,
  filterOpportunities,
  fixtureOpportunityCounts,
  groupOpportunitiesByFixture,
  isIsoDate,
  isScanRunning,
  nextVisibleLimit,
  shiftIsoDate,
  sliceProgressive,
  sortFixtureGroups,
  sortOpportunities,
  sortOpportunitiesWithinFixture,
} from './betBuilderUtils'

function baseOp(overrides: Partial<BetBuilderOpportunity> = {}): BetBuilderOpportunity {
  return {
    opportunity_key: 'k1',
    fixture: {
      today_fixture_id: 1,
      kickoff: '2026-08-08T11:00:00Z',
      country: 'Sweden',
      league: 'Division 2',
      home: { name: 'Onsala', logo: null },
      away: { name: 'Boljan', logo: null },
    },
    market: { market_key: 'DRAW', label: 'X' },
    origin: 'price',
    price_value: {
      present: true,
      method: 'v31_theoretical_gate_v1',
      quota_book: 4.1,
      quota_cecchino: 2.26,
      prob_book: null,
      prob_cecchino: null,
      vantaggio_prob: null,
      edge_pct: 81.42,
      score_acquisto: null,
      rating: 100,
      rating_label: 'Elite',
      status: 'ok',
    },
    signals: {
      available: true,
      present: true,
      evidence_mode: 'consensus',
      yes_count: 2,
      required_count: 4,
      available_count: 4,
      yes_columns: ['E', 'F'],
      passed: true,
    },
    purchasability_v31: {
      available: true,
      score: 86,
      class: 'Molto Alta',
      calculation_quality: 'full',
    },
    context_support: { available: false, reason: 'no_validated_context_module' },
    freshness: {},
    ...overrides,
  }
}

describe('betBuilderUtils', () => {
  it('validates iso dates and shifts days', () => {
    expect(isIsoDate('2026-08-08')).toBe(true)
    expect(isIsoDate('08-08-2026')).toBe(false)
    expect(shiftIsoDate('2026-08-08', -1)).toBe('2026-08-07')
    expect(shiftIsoDate('2026-08-08', 1)).toBe('2026-08-09')
  })

  it('filters by market and origin without hiding signal-only via price.present', () => {
    const ops = [
      baseOp({
        opportunity_key: 'price',
        origin: 'price',
        price_value: { ...baseOp().price_value, present: true },
      }),
      baseOp({
        opportunity_key: 'sig',
        origin: 'signals',
        market: { market_key: 'HOME', label: '1' },
        price_value: { ...baseOp().price_value, present: false },
        signals: { ...baseOp().signals, present: true },
      }),
      baseOp({
        opportunity_key: 'both',
        origin: 'price_and_signals',
        market: { market_key: 'DRAW', label: 'X' },
      }),
    ]

    const signalOnly = filterOpportunities(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      origin: 'signals',
    })
    expect(signalOnly.map((o) => o.opportunity_key)).toEqual(['sig'])
    expect(signalOnly[0].price_value.present).toBe(false)

    const draw = filterOpportunities(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      market: 'DRAW',
    })
    expect(draw.map((o) => o.opportunity_key).sort()).toEqual(['both', 'price'])
  })

  it('sorts purchasability desc with nulls last', () => {
    const ops = [
      baseOp({ opportunity_key: 'null', purchasability_v31: { available: false, score: null } }),
      baseOp({ opportunity_key: 'low', purchasability_v31: { available: true, score: 40 } }),
      baseOp({ opportunity_key: 'high', purchasability_v31: { available: true, score: 90 } }),
    ]
    const sorted = sortOpportunities(ops, 'purchasability_desc')
    expect(sorted.map((o) => o.opportunity_key)).toEqual(['high', 'low', 'null'])
  })

  it('sorts signals and edge', () => {
    const ops = [
      baseOp({
        opportunity_key: 'a',
        signals: { ...baseOp().signals, yes_count: 1 },
        price_value: { ...baseOp().price_value, edge_pct: 10 },
      }),
      baseOp({
        opportunity_key: 'b',
        signals: { ...baseOp().signals, yes_count: 4 },
        price_value: { ...baseOp().price_value, edge_pct: 50 },
      }),
    ]
    expect(sortOpportunities(ops, 'signals_desc').map((o) => o.opportunity_key)).toEqual([
      'b',
      'a',
    ])
    expect(sortOpportunities(ops, 'edge_desc').map((o) => o.opportunity_key)).toEqual(['b', 'a'])
  })

  it('progressive rendering helpers use PAGE_SIZE 12', () => {
    const items = Array.from({ length: 50 }, (_, i) => i)
    expect(BET_BUILDER_PAGE_SIZE).toBe(12)
    expect(sliceProgressive(items, BET_BUILDER_PAGE_SIZE)).toHaveLength(12)
    expect(nextVisibleLimit(12, 50)).toBe(24)
    expect(nextVisibleLimit(48, 50)).toBe(50)
  })

  it('filterAndSort combines search and sort', () => {
    const ops = [
      baseOp({
        opportunity_key: '1',
        fixture: { ...baseOp().fixture, home: { name: 'Alpha' } },
        purchasability_v31: { available: true, score: 10 },
      }),
      baseOp({
        opportunity_key: '2',
        fixture: { ...baseOp().fixture, home: { name: 'Beta' }, away: { name: 'Alpha' } },
        purchasability_v31: { available: true, score: 90 },
      }),
    ]
    const result = filterAndSortOpportunities(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      search: 'alpha',
    })
    expect(result.map((o) => o.opportunity_key)).toEqual(['2', '1'])
  })

  it('detects running scan status', () => {
    expect(isScanRunning('running')).toBe(true)
    expect(isScanRunning('queued')).toBe(true)
    expect(isScanRunning('completed')).toBe(false)
  })

  it('groups 3 opportunities of same fixture into 1 group preserving all', () => {
    const ops = [
      baseOp({
        opportunity_key: '1:DRAW',
        market: { market_key: 'DRAW', label: 'X' },
        purchasability_v31: { available: true, score: 60 },
      }),
      baseOp({
        opportunity_key: '1:ONE_X',
        market: { market_key: 'ONE_X', label: '1X' },
        purchasability_v31: { available: true, score: 86 },
        origin: 'price_and_signals',
      }),
      baseOp({
        opportunity_key: '1:OVER_2_5',
        market: { market_key: 'OVER_2_5', label: 'Over 2.5' },
        purchasability_v31: { available: true, score: 40 },
        origin: 'signals',
      }),
    ]
    const groups = groupOpportunitiesByFixture(ops)
    expect(groups).toHaveLength(1)
    expect(groups[0].todayFixtureId).toBe(1)
    expect(groups[0].opportunities).toHaveLength(3)
    expect(groups[0].opportunities.map((o) => o.opportunity_key)).toEqual([
      '1:ONE_X',
      '1:DRAW',
      '1:OVER_2_5',
    ])
    expect(groups[0].counts).toEqual({
      total: 3,
      price_only: 1,
      signals_only: 1,
      price_and_signals: 1,
    })
  })

  it('groups 2 fixtures into 2 groups; fixture without ops absent', () => {
    const ops = [
      baseOp({
        opportunity_key: '1:DRAW',
        fixture: { ...baseOp().fixture, today_fixture_id: 1 },
      }),
      baseOp({
        opportunity_key: '2:HOME',
        fixture: { ...baseOp().fixture, today_fixture_id: 2, home: { name: 'Other' } },
        market: { market_key: 'HOME', label: '1' },
      }),
    ]
    const groups = groupOpportunitiesByFixture(ops)
    expect(groups).toHaveLength(2)
    expect(groups.map((g) => g.todayFixtureId).sort()).toEqual([1, 2])
    expect(countUniqueFixtures(ops)).toBe(2)
  })

  it('sorts opportunities within fixture by V3.1 then origin price_and_signals', () => {
    const ops = [
      baseOp({
        opportunity_key: 'price',
        origin: 'price',
        purchasability_v31: { available: true, score: 80 },
      }),
      baseOp({
        opportunity_key: 'both',
        origin: 'price_and_signals',
        purchasability_v31: { available: true, score: 80 },
      }),
      baseOp({
        opportunity_key: 'sig',
        origin: 'signals',
        purchasability_v31: { available: true, score: 80 },
      }),
    ]
    expect(sortOpportunitiesWithinFixture(ops).map((o) => o.opportunity_key)).toEqual([
      'both',
      'sig',
      'price',
    ])
  })

  it('fixture sort uses max visible V3.1; null score does not win', () => {
    const groups = groupOpportunitiesByFixture([
      baseOp({
        opportunity_key: 'a-high',
        fixture: { ...baseOp().fixture, today_fixture_id: 10, home: { name: 'A' } },
        purchasability_v31: { available: true, score: 86 },
      }),
      baseOp({
        opportunity_key: 'a-low',
        fixture: { ...baseOp().fixture, today_fixture_id: 10, home: { name: 'A' } },
        market: { market_key: 'HOME', label: '1' },
        purchasability_v31: { available: true, score: 40 },
      }),
      baseOp({
        opportunity_key: 'b',
        fixture: { ...baseOp().fixture, today_fixture_id: 20, home: { name: 'B' } },
        purchasability_v31: { available: true, score: 80 },
      }),
      baseOp({
        opportunity_key: 'c-null',
        fixture: { ...baseOp().fixture, today_fixture_id: 30, home: { name: 'C' } },
        purchasability_v31: { available: false, score: null },
      }),
    ])
    const sorted = sortFixtureGroups(groups, 'purchasability_desc')
    expect(sorted.map((g) => g.todayFixtureId)).toEqual([10, 20, 30])
  })

  it('fixture sort by signals, edge, kickoff', () => {
    const ops = [
      baseOp({
        opportunity_key: 'a',
        fixture: {
          ...baseOp().fixture,
          today_fixture_id: 1,
          kickoff: '2026-08-08T18:00:00Z',
        },
        signals: { ...baseOp().signals, yes_count: 1 },
        price_value: { ...baseOp().price_value, edge_pct: 10 },
      }),
      baseOp({
        opportunity_key: 'b',
        fixture: {
          ...baseOp().fixture,
          today_fixture_id: 2,
          kickoff: '2026-08-08T12:00:00Z',
          home: { name: 'B' },
        },
        signals: { ...baseOp().signals, yes_count: 4 },
        price_value: { ...baseOp().price_value, edge_pct: 50 },
      }),
    ]
    const groups = groupOpportunitiesByFixture(ops)
    expect(sortFixtureGroups(groups, 'signals_desc').map((g) => g.todayFixtureId)).toEqual([2, 1])
    expect(sortFixtureGroups(groups, 'edge_desc').map((g) => g.todayFixtureId)).toEqual([2, 1])
    expect(sortFixtureGroups(groups, 'kickoff_asc').map((g) => g.todayFixtureId)).toEqual([2, 1])
  })

  it('buildBetBuilderFixtureGroups filters opportunity-first then groups', () => {
    const ops = [
      baseOp({
        opportunity_key: '1:DRAW',
        origin: 'price',
        market: { market_key: 'DRAW', label: 'X' },
        purchasability_v31: { available: true, score: 90 },
      }),
      baseOp({
        opportunity_key: '1:O25',
        origin: 'signals',
        market: { market_key: 'OVER_2_5', label: 'Over 2.5' },
        purchasability_v31: { available: true, score: 70 },
      }),
      baseOp({
        opportunity_key: '2:HOME',
        fixture: {
          ...baseOp().fixture,
          today_fixture_id: 2,
          country: 'Italy',
          league: 'Serie A',
          home: { name: 'Inter' },
          away: { name: 'Milan' },
        },
        origin: 'price',
        market: { market_key: 'HOME', label: '1' },
        purchasability_v31: { available: true, score: 50 },
      }),
    ]

    const byOrigin = buildBetBuilderFixtureGroups(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      origin: 'signals',
    })
    expect(byOrigin).toHaveLength(1)
    expect(byOrigin[0].opportunities.map((o) => o.opportunity_key)).toEqual(['1:O25'])

    const byMarket = buildBetBuilderFixtureGroups(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      market: 'DRAW',
    })
    expect(byMarket).toHaveLength(1)
    expect(byMarket[0].opportunities).toHaveLength(1)
    expect(byMarket[0].opportunities[0].market.market_key).toBe('DRAW')

    const byMin = buildBetBuilderFixtureGroups(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      minPurchasability: 80,
    })
    expect(byMin).toHaveLength(1)
    expect(byMin[0].opportunities[0].opportunity_key).toBe('1:DRAW')

    const byCountry = buildBetBuilderFixtureGroups(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      country: 'Italy',
    })
    expect(byCountry).toHaveLength(1)
    expect(byCountry[0].todayFixtureId).toBe(2)

    const byLeague = buildBetBuilderFixtureGroups(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      league: 'Serie A',
    })
    expect(byLeague).toHaveLength(1)

    const bySearch = buildBetBuilderFixtureGroups(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      search: 'onsala',
    })
    expect(bySearch).toHaveLength(1)
    expect(bySearch[0].todayFixtureId).toBe(1)
  })

  it('counts unique fixtures and filtered opportunities', () => {
    const ops = [
      baseOp({ opportunity_key: '1:a', fixture: { ...baseOp().fixture, today_fixture_id: 1 } }),
      baseOp({ opportunity_key: '1:b', fixture: { ...baseOp().fixture, today_fixture_id: 1 } }),
      baseOp({ opportunity_key: '2:a', fixture: { ...baseOp().fixture, today_fixture_id: 2 } }),
    ]
    expect(countUniqueFixtures(ops)).toBe(2)
    const groups = groupOpportunitiesByFixture(ops)
    expect(countFilteredOpportunities(groups)).toBe(3)
    expect(fixtureOpportunityCounts(ops.slice(0, 2)).total).toBe(2)
  })

  it('progressive slice does not split a fixture group', () => {
    const ops = Array.from({ length: 5 }, (_, i) =>
      baseOp({
        opportunity_key: `f${i}:DRAW`,
        fixture: { ...baseOp().fixture, today_fixture_id: i + 1 },
        purchasability_v31: { available: true, score: 100 - i },
      }),
    )
    // same fixture with 3 ops should stay together after slice (highest V3.1 → first)
    const multi = [
      baseOp({
        opportunity_key: '99:a',
        fixture: { ...baseOp().fixture, today_fixture_id: 99 },
        purchasability_v31: { available: true, score: 200 },
      }),
      baseOp({
        opportunity_key: '99:b',
        fixture: { ...baseOp().fixture, today_fixture_id: 99 },
        market: { market_key: 'HOME', label: '1' },
        purchasability_v31: { available: true, score: 198 },
      }),
      baseOp({
        opportunity_key: '99:c',
        fixture: { ...baseOp().fixture, today_fixture_id: 99 },
        market: { market_key: 'AWAY', label: '2' },
        purchasability_v31: { available: true, score: 197 },
      }),
      ...ops,
    ]
    const groups = buildBetBuilderFixtureGroups(multi, DEFAULT_BET_BUILDER_FILTERS)
    const visible = sliceProgressive(groups, 1)
    expect(visible).toHaveLength(1)
    expect(visible[0].todayFixtureId).toBe(99)
    expect(visible[0].opportunities).toHaveLength(3)
  })
})
