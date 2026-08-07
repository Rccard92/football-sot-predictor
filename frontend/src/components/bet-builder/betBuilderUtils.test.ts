import { describe, expect, it } from 'vitest'
import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import {
  BET_BUILDER_PAGE_SIZE,
  DEFAULT_BET_BUILDER_FILTERS,
  EVIDENCE_SORT_VERSION,
  buildBetBuilderFixtureGroups,
  compareOpportunityEvidenceStrength,
  countActiveFilters,
  countFilteredOpportunities,
  countUniqueFixtures,
  filterAndSortOpportunities,
  filterOpportunities,
  fixtureOpportunityCounts,
  formatPurchasabilityTab,
  getPrimaryOpportunity,
  groupOpportunitiesByFixture,
  isIsoDate,
  isScanRunning,
  nextVisibleLimit,
  originMicroLabel,
  resolveSelectedOpportunity,
  shiftIsoDate,
  sliceProgressive,
  sortFixtureGroups,
  sortOpportunities,
  sortOpportunitiesByEvidenceStrength,
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
  it('default filters use evidence_strength_desc and context all', () => {
    expect(DEFAULT_BET_BUILDER_FILTERS.sort).toBe('evidence_strength_desc')
    expect(DEFAULT_BET_BUILDER_FILTERS.context).toBe('all')
    expect(DEFAULT_BET_BUILDER_FILTERS.origin).toBe('all')
    expect(DEFAULT_BET_BUILDER_FILTERS.market).toBe('all')
    expect(DEFAULT_BET_BUILDER_FILTERS.minPurchasability).toBeNull()
    expect(EVIDENCE_SORT_VERSION).toBe('bet_builder_evidence_sort_v1')
  })

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

  it('filters by context available without inventing confirmation', () => {
    const ops = [
      baseOp({
        opportunity_key: 'with-ctx',
        context_support: { available: true, module: 'balance_v5', status: 'raw_context_only' },
      }),
      baseOp({
        opportunity_key: 'no-ctx',
        market: { market_key: 'HOME', label: '1' },
        context_support: { available: false, reason: 'no_validated_context_module' },
      }),
    ]
    const filtered = filterOpportunities(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      context: 'available',
    })
    expect(filtered.map((o) => o.opportunity_key)).toEqual(['with-ctx'])
  })

  describe('compareOpportunityEvidenceStrength', () => {
    it('A: price_and_signals before price', () => {
      const qs = baseOp({
        opportunity_key: 'qs',
        origin: 'price_and_signals',
        purchasability_v31: { available: true, score: 50 },
      })
      const price = baseOp({
        opportunity_key: 'price',
        origin: 'price',
        purchasability_v31: { available: true, score: 99 },
      })
      expect(compareOpportunityEvidenceStrength(qs, price)).toBeLessThan(0)
      expect(sortOpportunitiesByEvidenceStrength([price, qs]).map((o) => o.opportunity_key)).toEqual([
        'qs',
        'price',
      ])
    })

    it('B: higher consensus yes_count first at same origin', () => {
      const four = baseOp({
        opportunity_key: '4si',
        origin: 'price_and_signals',
        signals: { ...baseOp().signals, yes_count: 4, passed: true },
        purchasability_v31: { available: true, score: 70 },
      })
      const two = baseOp({
        opportunity_key: '2si',
        origin: 'price_and_signals',
        signals: { ...baseOp().signals, yes_count: 2, passed: true },
        purchasability_v31: { available: true, score: 70 },
      })
      expect(compareOpportunityEvidenceStrength(four, two)).toBeLessThan(0)
    })

    it('C: V3.1 score DESC when signal evidence equal', () => {
      const high = baseOp({
        opportunity_key: 'v90',
        origin: 'price_and_signals',
        signals: { ...baseOp().signals, yes_count: 3, passed: true },
        purchasability_v31: { available: true, score: 90 },
      })
      const low = baseOp({
        opportunity_key: 'v70',
        origin: 'price_and_signals',
        signals: { ...baseOp().signals, yes_count: 3, passed: true },
        purchasability_v31: { available: true, score: 70 },
      })
      expect(compareOpportunityEvidenceStrength(high, low)).toBeLessThan(0)
    })

    it('D: context available is only a tie-break', () => {
      const withCtx = baseOp({
        opportunity_key: 'ctx',
        origin: 'price',
        purchasability_v31: { available: true, score: 80 },
        price_value: { ...baseOp().price_value, rating: 80, edge_pct: 20 },
        signals: { ...baseOp().signals, yes_count: 0, passed: false },
        context_support: { available: true, module: 'balance_v5', status: 'raw_context_only' },
      })
      const noCtx = baseOp({
        opportunity_key: 'noct',
        origin: 'price',
        purchasability_v31: { available: true, score: 80 },
        price_value: { ...baseOp().price_value, rating: 80, edge_pct: 20 },
        signals: { ...baseOp().signals, yes_count: 0, passed: false },
        context_support: { available: false },
      })
      expect(compareOpportunityEvidenceStrength(withCtx, noCtx)).toBeLessThan(0)
    })

    it('E: rating DESC tie-break', () => {
      const high = baseOp({
        opportunity_key: 'r90',
        origin: 'price',
        purchasability_v31: { available: true, score: 70 },
        signals: { ...baseOp().signals, yes_count: 0, passed: false },
        price_value: { ...baseOp().price_value, rating: 90, edge_pct: 10 },
        context_support: { available: false },
      })
      const low = baseOp({
        opportunity_key: 'r70',
        origin: 'price',
        purchasability_v31: { available: true, score: 70 },
        signals: { ...baseOp().signals, yes_count: 0, passed: false },
        price_value: { ...baseOp().price_value, rating: 70, edge_pct: 10 },
        context_support: { available: false },
      })
      expect(compareOpportunityEvidenceStrength(high, low)).toBeLessThan(0)
    })

    it('F: edge DESC after rating', () => {
      const high = baseOp({
        opportunity_key: 'e30',
        origin: 'price',
        purchasability_v31: { available: true, score: 70 },
        signals: { ...baseOp().signals, yes_count: 0, passed: false },
        price_value: { ...baseOp().price_value, rating: 80, edge_pct: 30 },
        context_support: { available: false },
      })
      const low = baseOp({
        opportunity_key: 'e20',
        origin: 'price',
        purchasability_v31: { available: true, score: 70 },
        signals: { ...baseOp().signals, yes_count: 0, passed: false },
        price_value: { ...baseOp().price_value, rating: 80, edge_pct: 20 },
        context_support: { available: false },
      })
      expect(compareOpportunityEvidenceStrength(high, low)).toBeLessThan(0)
    })

    it('G: no combined score — comparator returns relative order only', () => {
      const a = baseOp({ opportunity_key: 'a', origin: 'signals' })
      const b = baseOp({ opportunity_key: 'b', origin: 'price' })
      const result = compareOpportunityEvidenceStrength(a, b)
      expect(typeof result).toBe('number')
      expect(result).not.toBe(0)
      expect((a as { evidence_score?: number }).evidence_score).toBeUndefined()
      expect((b as { strong_score?: number }).strong_score).toBeUndefined()
    })

    it('context available does not beat Q+S vs price-only', () => {
      const qs = baseOp({
        opportunity_key: 'qs',
        origin: 'price_and_signals',
        context_support: { available: false },
        purchasability_v31: { available: true, score: 40 },
      })
      const priceCtx = baseOp({
        opportunity_key: 'price-ctx',
        origin: 'price',
        context_support: { available: true, module: 'balance_v5', status: 'raw_context_only' },
        purchasability_v31: { available: true, score: 95 },
      })
      expect(compareOpportunityEvidenceStrength(qs, priceCtx)).toBeLessThan(0)
    })

    it('preserves direct_single_formula yes_count=1 without synthetic consensus', () => {
      const direct = baseOp({
        opportunity_key: 'home-direct',
        origin: 'signals',
        market: { market_key: 'HOME', label: '1' },
        signals: {
          available: true,
          present: true,
          evidence_mode: 'direct_single_formula',
          yes_count: 1,
          required_count: 1,
          available_count: 1,
          yes_columns: ['D'],
          passed: true,
        },
        purchasability_v31: { available: false, score: null },
      })
      const consensus2 = baseOp({
        opportunity_key: 'draw-2',
        origin: 'signals',
        signals: { ...baseOp().signals, yes_count: 2, passed: true },
        purchasability_v31: { available: false, score: null },
      })
      expect(direct.signals.yes_count).toBe(1)
      expect(direct.signals.evidence_mode).toBe('direct_single_formula')
      expect(compareOpportunityEvidenceStrength(consensus2, direct)).toBeLessThan(0)
    })

    it('signals.passed true before false', () => {
      const passed = baseOp({
        opportunity_key: 'pass',
        origin: 'signals',
        signals: { ...baseOp().signals, passed: true, yes_count: 1 },
      })
      const failed = baseOp({
        opportunity_key: 'fail',
        origin: 'signals',
        signals: { ...baseOp().signals, passed: false, yes_count: 4 },
      })
      expect(compareOpportunityEvidenceStrength(passed, failed)).toBeLessThan(0)
    })
  })

  it('primary prefers Q+S with lower V3.1 over price-only with higher V3.1', () => {
    const ops = [
      baseOp({
        opportunity_key: '1x-price',
        origin: 'price',
        market: { market_key: 'ONE_X', label: '1X' },
        purchasability_v31: { available: true, score: 90 },
        signals: { ...baseOp().signals, yes_count: 0, passed: false, present: false },
      }),
      baseOp({
        opportunity_key: 'x-qs',
        origin: 'price_and_signals',
        market: { market_key: 'DRAW', label: 'X' },
        purchasability_v31: { available: true, score: 70 },
        signals: { ...baseOp().signals, yes_count: 4, passed: true },
      }),
    ]
    const group = groupOpportunitiesByFixture(ops)[0]
    expect(getPrimaryOpportunity(group)?.opportunity_key).toBe('x-qs')
    expect(getPrimaryOpportunity(group)?.market.label).toBe('X')
  })

  it('fixture evidence_strength_desc uses primary opportunity', () => {
    const groups = groupOpportunitiesByFixture([
      baseOp({
        opportunity_key: 'a-qs',
        fixture: { ...baseOp().fixture, today_fixture_id: 1, home: { name: 'A' } },
        origin: 'price_and_signals',
        signals: { ...baseOp().signals, yes_count: 4, passed: true },
        purchasability_v31: { available: true, score: 80 },
      }),
      baseOp({
        opportunity_key: 'b-price',
        fixture: { ...baseOp().fixture, today_fixture_id: 2, home: { name: 'B' } },
        origin: 'price',
        purchasability_v31: { available: true, score: 95 },
        signals: { ...baseOp().signals, yes_count: 0, passed: false },
      }),
    ])
    const sorted = sortFixtureGroups(groups, 'evidence_strength_desc')
    expect(sorted.map((g) => g.todayFixtureId)).toEqual([1, 2])
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
    // evidence-first: Q+S → signals → price
    expect(groups[0].opportunities.map((o) => o.opportunity_key)).toEqual([
      '1:ONE_X',
      '1:OVER_2_5',
      '1:DRAW',
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

  it('sorts opportunities within fixture by origin Q+S > signals > price', () => {
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

  it('primary opportunity is first after evidence-first sort — not a new score', () => {
    const ops = [
      baseOp({
        opportunity_key: 'low',
        market: { market_key: 'AWAY', label: '2' },
        purchasability_v31: { available: true, score: 40 },
      }),
      baseOp({
        opportunity_key: 'high',
        market: { market_key: 'DRAW', label: 'X' },
        purchasability_v31: { available: true, score: 90 },
      }),
      baseOp({
        opportunity_key: 'mid',
        market: { market_key: 'HOME', label: '1' },
        purchasability_v31: { available: true, score: 70 },
      }),
    ]
    const group = groupOpportunitiesByFixture(ops)[0]
    const primary = getPrimaryOpportunity(group)
    expect(primary?.opportunity_key).toBe('high')
    expect(primary).toBe(group.opportunities[0])
  })

  it('single opportunity: primary equals only item', () => {
    const group = groupOpportunitiesByFixture([baseOp({ opportunity_key: 'only' })])[0]
    expect(group.opportunities).toHaveLength(1)
    expect(getPrimaryOpportunity(group)?.opportunity_key).toBe('only')
  })

  it('resolveSelectedOpportunity falls back when key missing or removed', () => {
    const ops = sortOpportunitiesWithinFixture([
      baseOp({
        opportunity_key: 'a',
        purchasability_v31: { available: true, score: 90 },
      }),
      baseOp({
        opportunity_key: 'b',
        market: { market_key: 'HOME', label: '1' },
        purchasability_v31: { available: true, score: 70 },
      }),
    ])
    expect(resolveSelectedOpportunity(ops, 'b')?.opportunity_key).toBe('b')
    expect(resolveSelectedOpportunity(ops, 'gone')?.opportunity_key).toBe('a')
    expect(resolveSelectedOpportunity(ops, null)?.opportunity_key).toBe('a')
    expect(resolveSelectedOpportunity([], 'a')).toBeNull()
  })

  it('primary after filter is first visible opportunity', () => {
    const ops = [
      baseOp({
        opportunity_key: 'draw',
        market: { market_key: 'DRAW', label: 'X' },
        purchasability_v31: { available: true, score: 95 },
      }),
      baseOp({
        opportunity_key: 'home',
        market: { market_key: 'HOME', label: '1' },
        purchasability_v31: { available: true, score: 60 },
      }),
    ]
    const filtered = buildBetBuilderFixtureGroups(ops, {
      ...DEFAULT_BET_BUILDER_FILTERS,
      market: 'HOME',
    })
    expect(getPrimaryOpportunity(filtered[0])?.opportunity_key).toBe('home')
  })

  it('formatPurchasabilityTab handles null V3.1 as N/D', () => {
    expect(formatPurchasabilityTab(86)).toBe('86')
    expect(formatPurchasabilityTab(null)).toBe('N/D')
    expect(formatPurchasabilityTab(undefined)).toBe('N/D')
  })

  it('origin micro labels and active filter count', () => {
    expect(originMicroLabel('price')).toBe('Quota')
    expect(originMicroLabel('signals')).toBe('Segnali')
    expect(originMicroLabel('price_and_signals')).toBe('Q + S')
    expect(countActiveFilters(DEFAULT_BET_BUILDER_FILTERS)).toBe(0)
    expect(
      countActiveFilters({
        ...DEFAULT_BET_BUILDER_FILTERS,
        origin: 'signals',
        context: 'available',
        country: 'Italy',
        search: 'Inter',
        minPurchasability: 70,
      }),
    ).toBe(4)
  })

  it('mobile selector data: label + V3.1 + origin for each opportunity', () => {
    const group = groupOpportunitiesByFixture([
      baseOp({
        opportunity_key: 'x',
        market: { market_key: 'DRAW', label: 'X' },
        purchasability_v31: { available: true, score: 86 },
        origin: 'price_and_signals',
      }),
      baseOp({
        opportunity_key: 'ox',
        market: { market_key: 'ONE_X', label: '1X' },
        purchasability_v31: { available: true, score: 71 },
        origin: 'price',
      }),
      baseOp({
        opportunity_key: 'nd',
        market: { market_key: 'OVER_2_5', label: 'Over 2.5' },
        purchasability_v31: { available: false, score: null },
        origin: 'signals',
      }),
    ])[0]
    const selectorData = group.opportunities.map((o) => ({
      label: o.market.label,
      score: formatPurchasabilityTab(o.purchasability_v31.score),
      origin: originMicroLabel(o.origin),
      isPrimary: o.opportunity_key === getPrimaryOpportunity(group)?.opportunity_key,
    }))
    expect(selectorData[0]).toEqual({
      label: 'X',
      score: '86',
      origin: 'Q + S',
      isPrimary: true,
    })
    // evidence order: Q+S, signals, price → N/D is middle
    expect(selectorData[1].score).toBe('N/D')
    expect(selectorData[2].label).toBe('1X')
  })
})
