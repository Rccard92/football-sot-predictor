import { useCallback, useEffect, useRef, useState } from 'react'
import { formatFetchError } from '../../utils/formatFetchError'

type QueryState<T> = {
  key: string
  data: T | null
  error: string | null
}

export type V4Query<T> = {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * Fetch con AbortController per effetto: la richiesta in volo viene annullata quando cambia la
 * chiave o il componente si smonta, e una risposta arrivata in ritardo viene ignorata.
 * `key === null` disattiva la richiesta.
 */
export function useV4Query<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
): V4Query<T> {
  const [nonce, setNonce] = useState(0)
  const [state, setState] = useState<QueryState<T>>({ key: '', data: null, error: null })
  const fetcherRef = useRef(fetcher)

  useEffect(() => {
    fetcherRef.current = fetcher
  })

  const fullKey = key == null ? null : `${key}#${nonce}`

  useEffect(() => {
    if (fullKey == null) return
    const controller = new AbortController()
    fetcherRef.current(controller.signal).then(
      (data) => {
        if (controller.signal.aborted) return
        setState({ key: fullKey, data, error: null })
      },
      (err: unknown) => {
        if (controller.signal.aborted) return
        setState({ key: fullKey, data: null, error: formatFetchError(err) })
      },
    )
    return () => controller.abort()
  }, [fullKey])

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  const active = fullKey != null && state.key === fullKey
  return {
    data: active ? state.data : null,
    error: active ? state.error : null,
    loading: fullKey != null && !active,
    reload,
  }
}
