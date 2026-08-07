import { describe, expect, it } from 'vitest'
import type { BetBuilderOpportunity } from '../../lib/cecchinoBetBuilderApi'
import {
  BET_BUILDER_PAGE_SIZE,
  DEFAULT_BET_BUILDER_FILTERS,
  filterAndSortOpportunities,
  filterOpportunities,
  isIsoDate,
  isScanRunning,
  nextVisibleLimit,
  shiftIsoDate,
  sliceProgressive,
  sortOpportunities,
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
      method: 'book_gt_cecchino_v1',
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

  it('progressive rendering helpers', () => {
    const items = Array.from({ length: 50 }, (_, i) => i)
    expect(sliceProgressive(items, BET_BUILDER_PAGE_SIZE)).toHaveLength(24)
    expect(nextVisibleLimit(24, 50)).toBe(48)
    expect(nextVisibleLimit(48, 50)).toBe(50)
  })

  it('filterAndSort combines search and sort', () => {
    const ops = [
      baseOp({ opportunity_key: '1', fixture: { ...baseOp().fixture, home: { name: 'Alpha' } }, purchasability_v31: { available: true, score: 10 } }),
      baseOp({ opportunity_key: '2', fixture: { ...baseOp().fixture, home: { name: 'Beta' }, away: { name: 'Alpha' } }, purchasability_v31: { available: true, score: 90 } }),
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
})
