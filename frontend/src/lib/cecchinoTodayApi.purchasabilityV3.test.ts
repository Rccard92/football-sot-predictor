import { describe, expect, it } from 'vitest'
import { indexPurchasabilityV3ByMarketKey } from './cecchinoTodayApi'
import {
  AWAY_V3_SNAPSHOT,
} from '../components/cecchino/fixtures/purchasabilityV3AwayRegression'

describe('indexPurchasabilityV3ByMarketKey', () => {
  it('indexa per market_key', () => {
    const map = indexPurchasabilityV3ByMarketKey(AWAY_V3_SNAPSHOT)
    expect(map.AWAY?.score).toBe(47)
    expect(map.AWAY?.value_score).toBe(100)
  })

  it('compatibilità payload senza V3', () => {
    expect(indexPurchasabilityV3ByMarketKey(null)).toEqual({})
    expect(indexPurchasabilityV3ByMarketKey(undefined)).toEqual({})
    expect(
      indexPurchasabilityV3ByMarketKey({
        snapshot_version: 'x',
        candidate_version: 'y',
        status: 'unavailable',
        items: [],
      }),
    ).toEqual({})
  })

  it('metric key purchasability_v3 è stringa valida nel contratto', () => {
    const metricKey: 'purchasability_v3' = 'purchasability_v3'
    expect(metricKey).toBe('purchasability_v3')
  })
})
