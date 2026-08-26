import { describe, expect, it } from 'vitest'
import {
  defaultV36SelectedMarketKey,
  formatV36FinalScore,
  listInactiveV36Markets,
  listScoredV36Markets,
  PANEL_MARKET_KEYS,
} from './cecchinoPurchasabilityV36UiUtils'
import {
  DRAW_V36_ITEM,
  GATE_FAILED_V36_ITEM,
  HOME_V36_ITEM,
  OVER_25_V36_ITEM,
  V36_VALID_SNAPSHOT,
} from './fixtures/purchasabilityV36Fixtures'
import { indexPurchasabilityV36ByMarketKey } from '../../lib/cecchinoTodayApi'

describe('cecchinoPurchasabilityV36UiUtils', () => {
  const byMarket = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)

  it('PANEL_MARKET_KEYS ha 19 mercati', () => {
    expect(PANEL_MARKET_KEYS).toHaveLength(19)
  })

  it('ordina mercati score per raw_score DESC', () => {
    const scored = listScoredV36Markets(byMarket)
    expect(scored.map((i) => i.market_key)).toEqual(['DRAW', 'HOME', 'OVER_2_5', 'AWAY'])
    expect(scored[0].raw_score).toBeGreaterThan(scored[1].raw_score!)
  })

  it('default selected = max raw_score', () => {
    expect(defaultV36SelectedMarketKey(byMarket)).toBe('DRAW')
  })

  it('formatV36FinalScore è N / 100 senza %', () => {
    expect(formatV36FinalScore(47)).toBe('47 / 100')
    expect(formatV36FinalScore(47)).not.toContain('%')
  })

  it('inactive markets restano gate_failed/not_calculable', () => {
    const inactive = listInactiveV36Markets({
      HOME: HOME_V36_ITEM,
      UNDER_2_5: GATE_FAILED_V36_ITEM,
      DRAW: DRAW_V36_ITEM,
      OVER_2_5: OVER_25_V36_ITEM,
    })
    expect(inactive.some((i) => i.market_key === 'UNDER_2_5')).toBe(true)
    expect(inactive.every((i) => i.status !== 'score')).toBe(true)
  })
})
