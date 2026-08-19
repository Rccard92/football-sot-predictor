import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  __getHistoricalReliabilityCacheSizeForTests,
  __resetHistoricalReliabilityCacheForTests,
  buildHistoricalReliabilityCacheKey,
  fetchHistoricalReliabilityCached,
  HISTORICAL_RELIABILITY_CACHE_TTL_MS,
  invalidateHistoricalReliabilityCache,
} from './historicalReliabilityCache'
import type { HistoricalReliabilityResponse } from './cecchinoKpiSignalsApi'

vi.mock('./cecchinoKpiSignalsApi', () => ({
  getHistoricalReliability: vi.fn(),
}))

import { getHistoricalReliability } from './cecchinoKpiSignalsApi'

const mockGet = vi.mocked(getHistoricalReliability)

function fakeResponse(): HistoricalReliabilityResponse {
  return {
    version: 'cecchino_historical_reliability_v1_1',
    status: 'ok',
    items: {
      '1:HOME': { market_key: 'HOME', today_fixture_id: 1, score: 61 },
    },
  }
}

describe('historicalReliabilityCache', () => {
  afterEach(() => {
    __resetHistoricalReliabilityCacheForTests()
    vi.clearAllMocks()
  })

  it('prima richiesta chiama API', async () => {
    mockGet.mockResolvedValueOnce(fakeResponse())
    const res = await fetchHistoricalReliabilityCached({
      date_from: '2026-08-19',
      date_to: '2026-08-19',
      competition_id: 50,
    })
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(res.items['1:HOME'].score).toBe(61)
  })

  it('seconda richiesta stessa key entro TTL riusa cache', async () => {
    mockGet.mockResolvedValueOnce(fakeResponse())
    const params = {
      date_from: '2026-08-19',
      date_to: '2026-08-19',
      competition_id: 50,
    }
    await fetchHistoricalReliabilityCached(params)
    await fetchHistoricalReliabilityCached(params)
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(__getHistoricalReliabilityCacheSizeForTests()).toBe(1)
  })

  it('richieste concorrenti vengono deduplicate', async () => {
    mockGet.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve(fakeResponse()), 20)
        }),
    )
    const params = {
      date_from: '2026-08-19',
      date_to: '2026-08-19',
      competition_id: null,
    }
    const [a, b] = await Promise.all([
      fetchHistoricalReliabilityCached(params),
      fetchHistoricalReliabilityCached(params),
    ])
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(a).toBe(b)
  })

  it('errore non avvelena cache', async () => {
    mockGet.mockRejectedValueOnce(new Error('network'))
    await expect(
      fetchHistoricalReliabilityCached({
        date_from: '2026-08-19',
        date_to: '2026-08-19',
      }),
    ).rejects.toThrow('network')
    expect(__getHistoricalReliabilityCacheSizeForTests()).toBe(0)

    mockGet.mockResolvedValueOnce(fakeResponse())
    await fetchHistoricalReliabilityCached({
      date_from: '2026-08-19',
      date_to: '2026-08-19',
    })
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('cambio date o competition genera nuova richiesta', async () => {
    mockGet.mockResolvedValue(fakeResponse())
    await fetchHistoricalReliabilityCached({
      date_from: '2026-08-19',
      date_to: '2026-08-19',
      competition_id: 50,
    })
    await fetchHistoricalReliabilityCached({
      date_from: '2026-08-20',
      date_to: '2026-08-20',
      competition_id: 50,
    })
    await fetchHistoricalReliabilityCached({
      date_from: '2026-08-19',
      date_to: '2026-08-19',
      competition_id: 51,
    })
    expect(mockGet).toHaveBeenCalledTimes(3)
  })

  it('invalidateHistoricalReliabilityCache forza refetch', async () => {
    mockGet.mockResolvedValue(fakeResponse())
    const params = { date_from: '2026-08-19', date_to: '2026-08-19' }
    await fetchHistoricalReliabilityCached(params)
    invalidateHistoricalReliabilityCache()
    await fetchHistoricalReliabilityCached(params)
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('buildHistoricalReliabilityCacheKey distingue competition', () => {
    expect(buildHistoricalReliabilityCacheKey('2026-08-19', 50)).toBe('2026-08-19|50')
    expect(buildHistoricalReliabilityCacheKey('2026-08-19', null)).toBe('2026-08-19|all')
  })

  it('TTL scaduto provoca nuova richiesta', async () => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue(fakeResponse())
    const params = { date_from: '2026-08-19', date_to: '2026-08-19' }
    await fetchHistoricalReliabilityCached(params)
    vi.advanceTimersByTime(HISTORICAL_RELIABILITY_CACHE_TTL_MS + 1)
    await fetchHistoricalReliabilityCached(params)
    expect(mockGet).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })
})
