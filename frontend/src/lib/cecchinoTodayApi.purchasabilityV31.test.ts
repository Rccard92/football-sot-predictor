import { describe, expect, it } from 'vitest'
import { indexPurchasabilityV31ByMarketKey } from './cecchinoTodayApi'
import { V31_SNAPSHOT } from '../components/cecchino/fixtures/purchasabilityV31Fixtures'

describe('indexPurchasabilityV31ByMarketKey', () => {
  it('indexa per market_key correttamente', () => {
    const map = indexPurchasabilityV31ByMarketKey(V31_SNAPSHOT)
    expect(map.AWAY?.score).toBe(52)
    expect(map.AWAY?.status).toBe('score')
    expect(map.AWAY?.historical_factor).toBe(0.6)
  })

  it('include tutti gli item del snapshot', () => {
    const map = indexPurchasabilityV31ByMarketKey(V31_SNAPSHOT)
    expect(Object.keys(map).length).toBe(3)
    expect(map.AWAY).toBeTruthy()
    expect(map.HOME).toBeTruthy()
    expect(map.DRAW).toBeTruthy()
  })

  it('item gate_failed ha score null', () => {
    const map = indexPurchasabilityV31ByMarketKey(V31_SNAPSHOT)
    expect(map.HOME?.score).toBeNull()
    expect(map.HOME?.status).toBe('gate_failed')
    expect(map.HOME?.reason_code).toBe('rating_below_50')
  })

  it('compatibilità payload senza V3.1', () => {
    expect(indexPurchasabilityV31ByMarketKey(null)).toEqual({})
    expect(indexPurchasabilityV31ByMarketKey(undefined)).toEqual({})
    expect(
      indexPurchasabilityV31ByMarketKey({
        snapshot_version: 'x',
        candidate_version: 'y',
        status: 'unavailable',
        items: [],
      }),
    ).toEqual({})
  })

  it('metric key purchasability_v31 è stringa valida nel contratto', () => {
    const metricKey: 'purchasability_v31' = 'purchasability_v31'
    expect(metricKey).toBe('purchasability_v31')
  })

  it('status score/score_provisional/gate_failed/non_calculable sono i valori previsti', () => {
    const validStatuses = ['score', 'score_provisional', 'gate_failed', 'non_calculable']
    for (const item of V31_SNAPSHOT.items) {
      expect(validStatuses).toContain(item.status)
    }
  })
})
