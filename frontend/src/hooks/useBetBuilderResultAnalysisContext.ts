import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchBetBuilderResultAnalysisContext,
  type BetBuilderResultAnalysisContext,
} from '../lib/cecchinoBetBuilderApi'

const sessionCache = new Map<number, BetBuilderResultAnalysisContext>()
const inflight = new Map<number, Promise<BetBuilderResultAnalysisContext>>()

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
      if (!bypassCache && sessionCache.has(fixtureId)) {
        setState({ status: 'success', data: sessionCache.get(fixtureId)! })
        return
      }

      const requestId = ++requestIdRef.current
      setState({ status: 'loading' })

      let promise = inflight.get(fixtureId)
      if (!promise || bypassCache) {
        const controller = new AbortController()
        promise = fetchBetBuilderResultAnalysisContext(fixtureId, controller.signal)
        inflight.set(fixtureId, promise)
        promise.finally(() => {
          if (inflight.get(fixtureId) === promise) {
            inflight.delete(fixtureId)
          }
        })
      }

      try {
        const data = await promise
        if (requestId !== requestIdRef.current) return
        sessionCache.set(fixtureId, data)
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
