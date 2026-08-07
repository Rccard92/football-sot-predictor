import { describe, expect, it } from 'vitest'
import type { BetBuilderOpportunity } from '../../../lib/cecchinoBetBuilderApi'
import {
  BET_BUILDER_CART_VERSION,
  addCartSelection,
  calculateCombinedOdds,
  cartStorageKey,
  clearCart,
  diffCartReconcile,
  emptyCartState,
  findCartItemByFixture,
  formatCombinedOddsDisplay,
  getCartCtaState,
  parseStoredCart,
  reconcileCart,
  removeCartSelection,
  replaceFixtureSelection,
  serializeStoredCart,
} from './betBuilderCartUtils'

function baseOp(overrides: Partial<BetBuilderOpportunity> = {}): BetBuilderOpportunity {
  return {
    opportunity_key: '10:DRAW',
    fixture: {
      today_fixture_id: 10,
      kickoff: '2026-08-08T11:00:00Z',
      country: 'Sweden',
      league: 'Division 2',
      home: { name: 'Onsala', logo: null },
      away: { name: 'Boljan', logo: null },
    },
    market: { market_key: 'DRAW', label: 'X' },
    origin: 'price_and_signals',
    price_value: {
      present: true,
      method: 'v31_theoretical_gate_v1',
      quota_book: 2.1,
      quota_cecchino: 1.8,
      prob_book: null,
      prob_cecchino: null,
      vantaggio_prob: null,
      edge_pct: 10,
      score_acquisto: null,
      rating: 80,
      rating_label: 'Alta',
      status: 'ok',
    },
    signals: {
      available: true,
      present: true,
      evidence_mode: 'consensus',
      yes_count: 2,
      required_count: 2,
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

const DATE = '2026-08-08'

describe('betBuilderCartUtils storage', () => {
  it('builds storage key per date', () => {
    expect(cartStorageKey(DATE)).toBe('sot.betBuilder.cart.v1:2026-08-08')
  })

  it('serializes and parses round-trip', () => {
    let state = emptyCartState(DATE)
    state = addCartSelection(state, baseOp(), 'rev-1', '2026-08-08T10:00:00.000Z')
    const raw = serializeStoredCart(state)
    const parsed = parseStoredCart(raw, DATE)
    expect(parsed.version).toBe(BET_BUILDER_CART_VERSION)
    expect(parsed.date).toBe(DATE)
    expect(parsed.items).toHaveLength(1)
    expect(parsed.items[0].opportunity_key).toBe('10:DRAW')
    expect(parsed.items[0].added_book_odds).toBe(2.1)
  })

  it('isolates carts by date', () => {
    const state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    const raw = serializeStoredCart(state)
    expect(parseStoredCart(raw, '2026-08-09').items).toHaveLength(0)
  })

  it('falls back to empty on corrupted JSON', () => {
    expect(parseStoredCart('{not-json', DATE).items).toHaveLength(0)
    expect(parseStoredCart(null, DATE).items).toHaveLength(0)
  })

  it('falls back to empty on unsupported version', () => {
    const raw = JSON.stringify({
      version: 'bet_builder_cart_v0',
      date: DATE,
      items: [{ opportunity_key: 'x' }],
    })
    expect(parseStoredCart(raw, DATE).items).toHaveLength(0)
  })

  it('falls back to empty on invalid shape', () => {
    const raw = JSON.stringify({
      version: BET_BUILDER_CART_VERSION,
      date: DATE,
      items: [{ today_fixture_id: 'bad' }],
    })
    expect(parseStoredCart(raw, DATE).items).toHaveLength(0)
  })
})

describe('betBuilderCartUtils same-fixture policy', () => {
  it('A: empty cart add X fixture 10', () => {
    const state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    expect(state.items).toHaveLength(1)
    expect(state.items[0].market_label).toBe('X')
  })

  it('B: CTA replace when same fixture different market', () => {
    const state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    const o25 = baseOp({
      opportunity_key: '10:O25',
      market: { market_key: 'OVER_25', label: 'Over 2.5' },
      price_value: { ...baseOp().price_value, quota_book: 1.9 },
    })
    const cta = getCartCtaState(state, o25)
    expect(cta.kind).toBe('replace')
    expect(cta.label).toMatch(/Sostituisci X con Over 2\.5/)
  })

  it('C: replace leaves only new market', () => {
    let state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    const o25 = baseOp({
      opportunity_key: '10:O25',
      market: { market_key: 'OVER_25', label: 'Over 2.5' },
    })
    expect(() => addCartSelection(state, o25, 'rev-1')).toThrow('FIXTURE_ALREADY_SELECTED')
    state = replaceFixtureSelection(state, o25, 'rev-2')
    expect(state.items).toHaveLength(1)
    expect(state.items[0].opportunity_key).toBe('10:O25')
  })

  it('D: different fixtures both allowed', () => {
    let state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    state = addCartSelection(
      state,
      baseOp({
        opportunity_key: '11:DRAW',
        fixture: { ...baseOp().fixture, today_fixture_id: 11, home: { name: 'Other' } },
      }),
      'rev-1',
    )
    expect(state.items).toHaveLength(2)
  })

  it('added CTA for exact opportunity', () => {
    const op = baseOp()
    const state = addCartSelection(emptyCartState(DATE), op, 'rev-1')
    expect(getCartCtaState(state, op).kind).toBe('added')
  })

  it('remove and clear', () => {
    let state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    state = addCartSelection(
      state,
      baseOp({
        opportunity_key: '11:DRAW',
        fixture: { ...baseOp().fixture, today_fixture_id: 11 },
      }),
      'rev-1',
    )
    state = removeCartSelection(state, {
      today_fixture_id: 10,
      opportunity_key: '10:DRAW',
    })
    expect(state.items).toHaveLength(1)
    expect(findCartItemByFixture(state, 10)).toBeUndefined()
    state = clearCart(state)
    expect(state.items).toHaveLength(0)
  })
})

describe('betBuilderCartUtils reconcile', () => {
  it('A: current selection updates odds 2.10 → 2.00 for multiplier', () => {
    const op = baseOp({ price_value: { ...baseOp().price_value, quota_book: 2.1 } })
    const state = addCartSelection(emptyCartState(DATE), op, 'rev-1')
    const updated = baseOp({ price_value: { ...baseOp().price_value, quota_book: 2.0 } })
    const resolved = reconcileCart(state, [updated])
    expect(resolved[0].status).toBe('current')
    expect(resolved[0].current_book_odds).toBe(2.0)
    expect(resolved[0].odds_changed).toBe(true)
    expect(calculateCombinedOdds(resolved)).toBe(2.0)
  })

  it('B: disappeared opportunity becomes stale and stays; multiplier N/D', () => {
    const state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    const resolved = reconcileCart(state, [])
    expect(resolved).toHaveLength(1)
    expect(resolved[0].status).toBe('stale')
    expect(calculateCombinedOdds(resolved)).toBeNull()
  })

  it('C: stale opportunity reappears as current', () => {
    const state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    const stale = reconcileCart(state, [])
    expect(stale[0].status).toBe('stale')
    const again = reconcileCart(state, [baseOp({ price_value: { ...baseOp().price_value, quota_book: 2.2 } })])
    expect(again[0].status).toBe('current')
    expect(again[0].current_book_odds).toBe(2.2)
    expect(again).toHaveLength(1)
  })

  it('D: filter hiding opportunity does not affect reconcile against full list', () => {
    const ops = [
      baseOp(),
      baseOp({
        opportunity_key: '11:O25',
        fixture: { ...baseOp().fixture, today_fixture_id: 11 },
        market: { market_key: 'OVER_25', label: 'Over 2.5' },
        price_value: { ...baseOp().price_value, quota_book: 1.8 },
      }),
    ]
    let state = addCartSelection(emptyCartState(DATE), ops[0], 'rev-1')
    state = addCartSelection(state, ops[1], 'rev-1')
    // Simulate filtered view empty — reconcile still uses full opportunities
    const filteredAway: BetBuilderOpportunity[] = []
    const againstFiltered = reconcileCart(state, filteredAway)
    expect(againstFiltered.every((i) => i.status === 'stale')).toBe(true)
    const againstFull = reconcileCart(state, ops)
    expect(againstFull.every((i) => i.status === 'current')).toBe(true)
    expect(againstFull).toHaveLength(2)
  })

  it('diffCartReconcile reports odds and stale transitions', () => {
    const state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    const prev = reconcileCart(state, [baseOp()])
    const nextOdds = reconcileCart(state, [
      baseOp({ price_value: { ...baseOp().price_value, quota_book: 1.95 } }),
    ])
    const oddsChanges = diffCartReconcile(prev, nextOdds)
    expect(oddsChanges).toEqual([
      expect.objectContaining({ type: 'odds_updated', from: 2.1, to: 1.95 }),
    ])
    const nextStale = reconcileCart(state, [])
    expect(diffCartReconcile(prev, nextStale)[0].type).toBe('became_stale')
    expect(diffCartReconcile(nextStale, prev)[0].type).toBe('became_current')
  })
})

describe('betBuilderCartUtils multiplier', () => {
  it('2.00 × 1.50 → 3.00', () => {
    let state = addCartSelection(
      emptyCartState(DATE),
      baseOp({ price_value: { ...baseOp().price_value, quota_book: 2.0 } }),
      'rev-1',
    )
    state = addCartSelection(
      state,
      baseOp({
        opportunity_key: '11:DRAW',
        fixture: { ...baseOp().fixture, today_fixture_id: 11 },
        price_value: { ...baseOp().price_value, quota_book: 1.5 },
      }),
      'rev-1',
    )
    const ops = [
      baseOp({ price_value: { ...baseOp().price_value, quota_book: 2.0 } }),
      baseOp({
        opportunity_key: '11:DRAW',
        fixture: { ...baseOp().fixture, today_fixture_id: 11 },
        price_value: { ...baseOp().price_value, quota_book: 1.5 },
      }),
    ]
    expect(calculateCombinedOdds(reconcileCart(state, ops))).toBe(3)
    expect(formatCombinedOddsDisplay(3)).toBe('3.00')
  })

  it('multi product with display rounding only at end', () => {
    const odds = [2.15, 1.91, 2.1]
    let state = emptyCartState(DATE)
    const ops: BetBuilderOpportunity[] = []
    odds.forEach((q, i) => {
      const id = 20 + i
      const op = baseOp({
        opportunity_key: `${id}:DRAW`,
        fixture: { ...baseOp().fixture, today_fixture_id: id },
        price_value: { ...baseOp().price_value, quota_book: q },
      })
      state = addCartSelection(state, op, 'rev-1')
      ops.push(op)
    })
    const product = 2.15 * 1.91 * 2.1
    const combined = calculateCombinedOdds(reconcileCart(state, ops))
    expect(combined).toBeCloseTo(product, 10)
    expect(formatCombinedOddsDisplay(combined)).toBe(product.toFixed(2))
  })

  it('single selection equals book odds', () => {
    const op = baseOp({ price_value: { ...baseOp().price_value, quota_book: 4.1 } })
    const state = addCartSelection(emptyCartState(DATE), op, 'rev-1')
    expect(calculateCombinedOdds(reconcileCart(state, [op]))).toBe(4.1)
  })

  it('missing odds → null / N/D', () => {
    const op = baseOp({ price_value: { ...baseOp().price_value, quota_book: null } })
    const state = addCartSelection(emptyCartState(DATE), op, 'rev-1')
    expect(calculateCombinedOdds(reconcileCart(state, [op]))).toBeNull()
    expect(formatCombinedOddsDisplay(null)).toBe('N/D')
    expect(getCartCtaState(emptyCartState(DATE), op).bookOddsMissing).toBe(true)
  })

  it('stale item → null', () => {
    const state = addCartSelection(emptyCartState(DATE), baseOp(), 'rev-1')
    expect(calculateCombinedOdds(reconcileCart(state, []))).toBeNull()
  })

  it('empty cart → null', () => {
    expect(calculateCombinedOdds([])).toBeNull()
  })
})
