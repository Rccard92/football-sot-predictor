/** Accesso amministratore in tutta l'app (dal 20/10/2026).
 *
 * I router /admin chiedono la sessione admin per le operazioni che scrivono o lanciano lavoro. Quando una
 * richiesta torna 401 "Sessione admin assente o scaduta", le funzioni di rete emettono questo evento e il
 * dialogo di login (AdminSessionGate, montato nel Layout) si apre. Dopo l'accesso basta ripetere il click.
 */

export const ADMIN_AUTH_REQUIRED_EVENT = 'cecchino:admin-auth-required'
export const ADMIN_AUTH_CHANGED_EVENT = 'cecchino:admin-auth-changed'

export function requestAdminLogin(reason?: string): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(ADMIN_AUTH_REQUIRED_EVENT, { detail: { reason } }))
}

export function announceAdminAuthChanged(authenticated: boolean): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(ADMIN_AUTH_CHANGED_EVENT, { detail: { authenticated } }))
}

/** 401 su un indirizzo /api/admin o con il messaggio della sessione: serve l'accesso. */
export function isAdminAuthFailure(status: number, url: string, message?: string): boolean {
  if (status !== 401) return false
  return url.includes('/api/admin') || /sessione admin/i.test(message ?? '')
}

let installed = false

/** Una volta all'avvio: le richieste al backend portano il cookie di sessione (frontend e backend sono su
 *  domini diversi) e un 401 dell'area admin apre il dialogo di accesso. Il contenuto delle richieste non
 *  cambia; le richieste verso altri domini restano come sono. */
export function installAdminFetchInterceptor(apiBase: string | undefined): void {
  if (installed || typeof window === 'undefined' || typeof window.fetch !== 'function') return
  const base = String(apiBase ?? '').replace(/\/+$/, '')
  if (!base) return
  installed = true
  const original = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (!url.startsWith(base)) return original(input, init)
    const res = await original(input, { ...init, credentials: init?.credentials ?? 'include' })
    if (res.status === 401 && isAdminAuthFailure(401, url) && !url.includes('/api/admin/auth/')) {
      requestAdminLogin()
    }
    return res
  }
}
