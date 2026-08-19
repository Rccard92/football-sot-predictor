import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION,
  fetchBetBuilderResultAnalysisContext,
  type BetBuilderResultAnalysisContext,
} from '../lib/cecchinoBetBuilderApi'

function cacheKey(fixtureId: number): string {
  return `${fixtureId}:${BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION}`
}

const sessionCache = new Map<string, BetBuilderResultAnalysisContext>()
const inflight = new Map<string, Promise<BetBuilderResultAnalysisContext>>()

export type AnalysisContextState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: BetBuilderResultAnalysisContext }
  | { status: 'error'; message: string }

export function useBetBuilderResultAnalysisContext(
  todayFixtureId: number | null | undefined,
  enabled: boolean,
) {
  const [state, setState] = useState<AnalysisContextState>({ status: 'idle' })
  const requestIdRef = useRef(0)

  const load = useCallback(
    async (fixtureId: number, bypassCache = false) => {
      const key = cacheKey(fixtureId)
      if (!bypassCache && sessionCache.has(key)) {
        setState({ status: 'success', data: sessionCache.get(key)! })
        return
      }

      const requestId = ++requestIdRef.current
      setState({ status: 'loading' })

      let promise = inflight.get(key)
      if (!promise || bypassCache) {
        const controller = new AbortController()
        promise = fetchBetBuilderResultAnalysisContext(fixtureId, controller.signal)
        inflight.set(key, promise)
        promise.finally(() => {
          if (inflight.get(key) === promise) {
            inflight.delete(key)
          }
        })
      }

      try {
        const data = await promise
        if (requestId !== requestIdRef.current) return
        if (data.contract_version !== BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION) {
          setState({ status: 'error', message: 'Contratto analisi tecnica non supportato.' })
          return
        }
        sessionCache.set(key, data)
        setState({ status: 'success', data })
      } catch (err) {
        if (requestId !== requestIdRef.current) return
        const message =
          err instanceof Error ? err.message : 'Analisi tecnica non disponibile.'
        setState({ status: 'error', message })
      }
    },
    [],
  )

  useEffect(() => {
    if (!enabled || todayFixtureId == null) {
      setState({ status: 'idle' })
      return
    }
    void load(todayFixtureId)
  }, [enabled, todayFixtureId, load])

  const retry = useCallback(() => {
    if (todayFixtureId == null) return
    void load(todayFixtureId, true)
  }, [todayFixtureId, load])

  return { state, retry }
}

export function __clearBetBuilderAnalysisContextCacheForTests() {
  sessionCache.clear()
  inflight.clear()
}
