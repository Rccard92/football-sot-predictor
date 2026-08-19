import { describe, expect, it } from 'vitest'
import type { CecchinoPurchasabilityV31Item } from '../../lib/cecchinoTodayApi'
import {
  defaultSelectedMarketKey,
  isActivePurchasabilityMarket,
  listActivePurchasabilityMarkets,
} from './cecchinoPurchasabilityUiUtils'

describe('cecchinoPurchasabilityUiUtils', () => {
  const active: CecchinoPurchasabilityV31Item = {
    market_key: 'X_TWO',
    status: 'score',
    score: 76,
    score_v31: 76,
  }
  const gateFailed: CecchinoPurchasabilityV31Item = {
    market_key: 'HOME',
    status: 'gate_failed',
    score: null,
  }

  it('isActivePurchasabilityMarket', () => {
    expect(isActivePurchasabilityMarket(active)).toBe(true)
    expect(isActivePurchasabilityMarket(gateFailed)).toBe(false)
  })

  it('ordina per score e ordine canonico', () => {
    const draw: CecchinoPurchasabilityV31Item = {
      market_key: 'DRAW',
      status: 'score',
      score: 76,
      score_v31: 76,
    }
    const map = { X_TWO: active, DRAW: draw }
    const sorted = listActivePurchasabilityMarkets(map)
    expect(sorted[0].market_key).toBe('DRAW')
    expect(defaultSelectedMarketKey(map)).toBe('DRAW')
  })
})
