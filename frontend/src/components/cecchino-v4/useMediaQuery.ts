import { useCallback, useSyncExternalStore } from 'react'

function hasMatchMedia(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
}

/** True quando la media query e' soddisfatta; senza `matchMedia` (SSR, test) vale `fallback`. */
export function useMediaQuery(query: string, fallback = true): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!hasMatchMedia()) return () => {}
      const mq = window.matchMedia(query)
      mq.addEventListener('change', onChange)
      return () => mq.removeEventListener('change', onChange)
    },
    [query],
  )
  const getSnapshot = useCallback(
    () => (hasMatchMedia() ? window.matchMedia(query).matches : fallback),
    [query, fallback],
  )
  const getServerSnapshot = useCallback(() => fallback, [fallback])
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}

/** Da 2xl (1536 px) il Ragionamento sta nel pannello a destra, sotto in drawer. */
export function useIsDesktopPanel(): boolean {
  return useMediaQuery('(min-width: 1536px)')
}
