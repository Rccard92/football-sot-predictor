import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchSportApiLineups, type LineupRefreshImpactDelta } from '../lib/api'

export function useSportApiLineupRefresh(opts: {
  fixtureId?: number | null
  season?: number
  regenerateV20?: boolean
  onDataRefresh?: () => void | Promise<void>
}) {
  const { fixtureId, regenerateV20 = false, onDataRefresh } = opts
  const [loading, setLoading] = useState(false)
  const [v20Loading, setV20Loading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [lastImpact, setLastImpact] = useState<LineupRefreshImpactDelta | null>(null)
  const successTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (successTimer.current) clearTimeout(successTimer.current)
    }
  }, [])

  const runRefresh = useCallback(async () => {
    const fid = fixtureId
    if (fid == null || loading || v20Loading) return
    if (!window.confirm('Aggiorna formazione SportAPI? Consuma 1 chiamata SportAPI.')) return

    setLoading(true)
    setError(null)
    setSuccessMessage(null)
    setLastImpact(null)

    try {
      if (regenerateV20) {
        setV20Loading(true)
      }
      const out = await fetchSportApiLineups(fid, {
        trackImpact: true,
        regenerateV20,
        timeoutMs: 120_000,
      })
      if (out?.status === 'error') {
        throw new Error(out.message ?? 'Refresh formazione non riuscito')
      }
      if (out.impact_delta) {
        setLastImpact(out.impact_delta)
      }
      await onDataRefresh?.()
      const imp = out.impact_delta
      if (imp?.direction_total && imp.delta_total_sot != null) {
        const arrow = imp.direction_total === 'UP' ? '↑' : imp.direction_total === 'DOWN' ? '↓' : '='
        const sign = imp.delta_total_sot > 0 ? '+' : ''
        setSuccessMessage(
          `Formazione aggiornata. Totale SOT: ${arrow} ${sign}${imp.delta_total_sot.toFixed(2)}${imp.main_reason ? ` — ${imp.main_reason}` : ''}`,
        )
      } else {
        setSuccessMessage('Formazione aggiornata.')
      }
      if (successTimer.current) clearTimeout(successTimer.current)
      successTimer.current = setTimeout(() => setSuccessMessage(null), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
      setV20Loading(false)
    }
  }, [fixtureId, loading, v20Loading, onDataRefresh, regenerateV20])

  const busy = loading || v20Loading

  return {
    runRefresh,
    loading,
    v20Loading,
    busy,
    error,
    successMessage,
    lastImpact,
    buttonLabel: loading ? 'Fetch…' : v20Loading ? 'Ricalcolo v2.0…' : 'Aggiorna formazione',
  }
}
