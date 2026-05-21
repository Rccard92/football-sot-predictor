import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DEFAULT_SEASON,
  fetchSportApiLineups,
  postRegenerateV20ForFixture,
} from '../lib/api'

export function useSportApiLineupRefresh(opts: {
  fixtureId?: number | null
  season?: number
  regenerateV20?: boolean
  onDataRefresh?: () => void | Promise<void>
}) {
  const { fixtureId, season = DEFAULT_SEASON, regenerateV20 = false, onDataRefresh } = opts
  const [loading, setLoading] = useState(false)
  const [v20Loading, setV20Loading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
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

    try {
      await fetchSportApiLineups(fid)
      if (regenerateV20) {
        setV20Loading(true)
        try {
          const out = (await postRegenerateV20ForFixture(season, fid)) as {
            status?: string
            message?: string
            predictions_ok?: number
          }
          if (out?.status === 'error') {
            throw new Error(out.message ?? 'Rigenerazione v2.0 non riuscita')
          }
          if ((out?.predictions_ok ?? 0) === 0 && out?.status !== 'success') {
            throw new Error(
              out?.message ??
                'Manca la base v1.1 per questa partita: genera v1.1 da Admin prima del ricalcolo v2.0.',
            )
          }
        } finally {
          setV20Loading(false)
        }
      }
      await onDataRefresh?.()
      setSuccessMessage('Formazione aggiornata.')
      if (successTimer.current) clearTimeout(successTimer.current)
      successTimer.current = setTimeout(() => setSuccessMessage(null), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [fixtureId, loading, v20Loading, onDataRefresh, regenerateV20, season])

  const busy = loading || v20Loading

  return {
    runRefresh,
    loading,
    v20Loading,
    busy,
    error,
    successMessage,
    buttonLabel: loading ? 'Fetch…' : v20Loading ? 'Ricalcolo v2.0…' : 'Aggiorna formazione',
  }
}
