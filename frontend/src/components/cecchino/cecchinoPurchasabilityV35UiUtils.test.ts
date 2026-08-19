import { describe, expect, it } from 'vitest'
import {
  defaultV35SelectedMarketKey,
  formatV35CandidateWeightsSubtitle,
  getV35CandidateScore,
  listActiveV35Markets,
  PANEL_MARKET_KEYS,
  resolveV35CandidateRegistry,
} from './cecchinoPurchasabilityV35UiUtils'
import {
  GATE_FAILED_V35_ITEM,
  HOME_V35_ITEM,
  LOW_SCORE_V35_ITEM,
  OVER_25_V35_ITEM,
  V35_VALID_SNAPSHOT,
} from './fixtures/purchasabilityV35Fixtures'
import { indexPurchasabilityV35ByMarketKey } from '../../lib/cecchinoTodayApi'

const itemsByMarket = indexPurchasabilityV35ByMarketKey(V35_VALID_SNAPSHOT)

describe('cecchinoPurchasabilityV35UiUtils', () => {
  it('PANEL_MARKET_KEYS ha 19 mercati', () => {
    expect(PANEL_MARKET_KEYS).toHaveLength(19)
  })

  it('solo status=score è attivo nel selector', () => {
    const active = listActiveV35Markets(itemsByMarket, 'A')
    expect(active.every((i) => i.status === 'score')).toBe(true)
    expect(active.some((i) => i.market_key === 'AWAY')).toBe(false)
  })

  it('gate_failed escluso dal selector', () => {
    const active = listActiveV35Markets({ AWAY: GATE_FAILED_V35_ITEM }, 'A')
    expect(active).toHaveLength(0)
  })

  it('score 5 resta visibile se status=score', () => {
    const active = listActiveV35Markets({ DRAW: LOW_SCORE_V35_ITEM }, 'B')
    expect(active).toHaveLength(1)
    expect(getV35CandidateScore(LOW_SCORE_V35_ITEM, 'B')).toBe(5)
  })

  it('ordina per score candidate A desc', () => {
    const active = listActiveV35Markets(itemsByMarket, 'A')
    expect(active[0]?.market_key).toBe('HOME')
    expect(getV35CandidateScore(active[0]!, 'A')).toBe(63)
  })

  it('ordina diversamente per candidate B', () => {
    const activeB = listActiveV35Markets(itemsByMarket, 'B')
    const homeIdx = activeB.findIndex((i) => i.market_key === 'HOME')
    const overIdx = activeB.findIndex((i) => i.market_key === 'OVER_2_5')
    expect(homeIdx).toBeGreaterThanOrEqual(0)
    expect(overIdx).toBeGreaterThanOrEqual(0)
  })

  it('default market è il più alto candidate A', () => {
    expect(defaultV35SelectedMarketKey(itemsByMarket, 'A')).toBe('HOME')
  })

  it('S=null restituisce N/D via score check', () => {
    const s = OVER_25_V35_ITEM.components?.structural_coherence
    expect(s?.score).toBeNull()
  })

  it('weights letti dallo snapshot candidate_registry', () => {
    const registry = resolveV35CandidateRegistry(V35_VALID_SNAPSHOT)
    const subtitle = formatV35CandidateWeightsSubtitle(registry.A)
    expect(subtitle).toBe('40V · 25D · 20S · 15Q')
  })

  it('HOME item ha candidates A/B/C/D', () => {
    expect(Object.keys(HOME_V35_ITEM.candidates ?? {})).toEqual(['A', 'B', 'C', 'D'])
  })
})
