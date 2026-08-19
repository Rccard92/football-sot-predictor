/**
 * Cache in-memory per Historical Reliability — chiave scanDate + competitionId.
 * TTL breve (90s), deduplica richieste concorrenti, errori non memorizzati.
 */

import {
  getHistoricalReliability,
  type HistoricalReliabilityResponse,
} from './cecchinoKpiSignalsApi'

/** TTL cache — allineato al backend (90s). */
export const HISTORICAL_RELIABILITY_CACHE_TTL_MS = 90_000

type CacheEntry = {
  fetchedAt: number
  data: HistoricalReliabilityResponse
}

const cache = new Map<string, CacheEntry>()
const inFlight = new Map<string, Promise<HistoricalReliabilityResponse>>()

export function buildHistoricalReliabilityCacheKey(
  scanDate: string,
  competitionId: number | null | undefined,
): string {
  return `${scanDate}|${competitionId ?? 'all'}`
}

export function invalidateHistoricalReliabilityCache(): void {
  cache.clear()
  inFlight.clear()
}

function isFresh(entry: CacheEntry, now: number): boolean {
  return now - entry.fetchedAt <= HISTORICAL_RELIABILITY_CACHE_TTL_MS
}

export async function fetchHistoricalReliabilityCached(params: {
  date_from: string
  date_to: string
  competition_id?: number | null
}): Promise<HistoricalReliabilityResponse> {
  const key = buildHistoricalReliabilityCacheKey(
    params.date_from,
    params.competition_id,
  )
  const now = Date.now()

  const cached = cache.get(key)
  if (cached && isFresh(cached, now)) {
    return cached.data
  }
  if (cached && !isFresh(cached, now)) {
    cache.delete(key)
  }

  const pending = inFlight.get(key)
  if (pending) {
    return pending
  }

  const promise = getHistoricalReliability(params)
    .then((data) => {
      cache.set(key, { fetchedAt: Date.now(), data })
      inFlight.delete(key)
      return data
    })
    .catch((err) => {
      inFlight.delete(key)
      throw err
    })

  inFlight.set(key, promise)
  return promise
}

/** Solo per test — reset stato interno. */
export function __resetHistoricalReliabilityCacheForTests(): void {
  invalidateHistoricalReliabilityCache()
}

/** Solo per test — ispeziona cache. */
export function __getHistoricalReliabilityCacheSizeForTests(): number {
  return cache.size
}
