/**
 * Single-flight + generation id per audit forensic.
 * Impedisce fetch duplicate e scarta risposte stale.
 */
export type AuditRequestGuard = {
  begin: () => { requestId: number; signal: AbortSignal } | null
  end: (requestId: number) => void
  isCurrent: (requestId: number) => boolean
  abort: () => void
  isInFlight: () => boolean
}

export function createAuditRequestGuard(): AuditRequestGuard {
  let inFlight = false
  let generation = 0
  let controller: AbortController | null = null

  return {
    begin() {
      if (inFlight) return null
      inFlight = true
      generation += 1
      const requestId = generation
      controller?.abort()
      controller = new AbortController()
      return { requestId, signal: controller.signal }
    },
    end(requestId: number) {
      if (requestId === generation) {
        inFlight = false
      }
    },
    isCurrent(requestId: number) {
      return requestId === generation
    },
    abort() {
      generation += 1
      inFlight = false
      try {
        controller?.abort()
      } catch {
        /* ignore */
      }
      controller = null
    },
    isInFlight() {
      return inFlight
    },
  }
}

export function isAuditTimeoutError(err: unknown): boolean {
  if (err == null) return false
  const msg =
    err instanceof Error
      ? err.message
      : typeof err === 'string'
        ? err
        : String((err as { message?: unknown }).message ?? err)
  const lower = msg.toLowerCase()
  return (
    lower.includes('timeout') ||
    lower.includes('aborted') ||
    lower.includes('abort') ||
    (typeof DOMException !== 'undefined' &&
      err instanceof DOMException &&
      err.name === 'AbortError')
  )
}

export const AUDIT_TIMEOUT_USER_MESSAGE =
  'La verifica completa richiede più tempo del previsto. I dati precedenti restano disponibili.'
