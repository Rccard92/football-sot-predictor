/** @vitest-environment node */
import { describe, expect, it } from 'vitest'
import {
  indexPurchasabilityV35ByMarketKey,
  type CecchinoPurchasabilityV35Snapshot,
} from './cecchinoTodayApi'
import { V35_VALID_SNAPSHOT } from '../components/cecchino/fixtures/purchasabilityV35Fixtures'

describe('indexPurchasabilityV35ByMarketKey', () => {
  it('indicizza 19 mercati', () => {
    const map = indexPurchasabilityV35ByMarketKey(V35_VALID_SNAPSHOT)
    expect(Object.keys(map)).toHaveLength(19)
  })

  it('restituisce mappa vuota se snapshot assente', () => {
    expect(indexPurchasabilityV35ByMarketKey(null)).toEqual({})
    expect(indexPurchasabilityV35ByMarketKey(undefined)).toEqual({})
  })

  it('accetta snapshot parziale legacy', () => {
    const partial: CecchinoPurchasabilityV35Snapshot = {
      items: [{ market_key: 'HOME', status: 'score' }],
    }
    const map = indexPurchasabilityV35ByMarketKey(partial)
    expect(map.HOME?.market_key).toBe('HOME')
  })
})
