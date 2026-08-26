import { describe, expect, it } from 'vitest'
import {
  indexPurchasabilityV36ByMarketKey,
  type V36Snapshot,
} from './cecchinoTodayApi'
import { V36_VALID_SNAPSHOT } from '../components/cecchino/fixtures/purchasabilityV36Fixtures'

describe('indexPurchasabilityV36ByMarketKey', () => {
  it('indicizza per market_key', () => {
    const map = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)
    expect(map.HOME?.score).toBe(47)
    expect(map.DRAW?.raw_score).toBe(55.8)
  })

  it('gestisce null/undefined/empty', () => {
    expect(indexPurchasabilityV36ByMarketKey(null)).toEqual({})
    expect(indexPurchasabilityV36ByMarketKey(undefined)).toEqual({})
    expect(
      indexPurchasabilityV36ByMarketKey({ items: [] } as V36Snapshot),
    ).toEqual({})
  })
})
