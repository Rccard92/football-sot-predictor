/** Schede e permessi (dal 29/10/2026). Le chiavi coincidono con il catalogo del backend
 *  (`app/core/access_control.py`): il backend blocca i dati, qui si nasconde il menu e si chiude la rotta. */

import { NAV_ALL, type NavItem } from './navItems'

/** L'Admin resta solo agli amministratori: non e' una scheda assegnabile. */
export const ADMIN_ONLY_TAB = 'admin'

export function tabKeyOfPath(path: string): string {
  return path.replace(/^\/+/, '').split(/[/?#]/)[0] ?? ''
}

/** Scheda a cui appartiene un indirizzo della dashboard (null = nessuna scheda, es. pagina inesistente). */
export function tabKeyForPathname(pathname: string): string | null {
  const p = pathname.replace(/\/+$/, '') || '/'
  if (p === '/' || p === '/cecchino') return 'cecchino-today'
  if (p === '/monitoraggio-segnali-lab' || p.startsWith('/cecchino/ricerca-')) return 'monitoraggio-moduli'
  const first = tabKeyOfPath(p)
  if (first === ADMIN_ONLY_TAB) return ADMIN_ONLY_TAB
  return NAV_ALL.some((item) => tabKeyOfPath(item.to) === first) ? first : null
}

export function canSeeTab(key: string | null, isAdmin: boolean, allowed: readonly string[]): boolean {
  if (isAdmin) return true
  if (key === null) return true
  if (key === ADMIN_ONLY_TAB) return false
  return allowed.includes(key)
}

export function visibleNavItems(items: NavItem[], isAdmin: boolean, allowed: readonly string[]): NavItem[] {
  return items.filter((item) => canSeeTab(tabKeyOfPath(item.to), isAdmin, allowed))
}

/** Prima scheda consentita, per mandare l'utente dove puo' stare. */
export function firstAllowedPath(isAdmin: boolean, allowed: readonly string[]): string | null {
  const item = NAV_ALL.find((i) => canSeeTab(tabKeyOfPath(i.to), isAdmin, allowed))
  return item ? item.to : null
}
