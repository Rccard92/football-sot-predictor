import { describe, expect, it } from 'vitest'
import { NAV_ALL } from './navItems'
import { canSeeTab, firstAllowedPath, tabKeyForPathname, visibleNavItems } from './tabAccess'

describe('schede per account (29/10/2026)', () => {
  it('ogni indirizzo della dashboard appartiene alla sua scheda', () => {
    expect(tabKeyForPathname('/')).toBe('cecchino-today')
    expect(tabKeyForPathname('/cecchino')).toBe('cecchino-today')
    expect(tabKeyForPathname('/cecchino-lab/purchasability-replay')).toBe('cecchino-lab')
    expect(tabKeyForPathname('/cecchino/ricerca-credibilita-x')).toBe('monitoraggio-moduli')
    expect(tabKeyForPathname('/monitoraggio-segnali-lab')).toBe('monitoraggio-moduli')
    expect(tabKeyForPathname('/admin')).toBe('admin')
    expect(tabKeyForPathname('/inesistente')).toBeNull()
  })

  it('un utente vede solo le schede assegnate, mai Admin', () => {
    const allowed = ['cecchino-today', 'bet-builder']
    expect(visibleNavItems(NAV_ALL, false, allowed).map((i) => i.to)).toEqual(['/cecchino-today', '/bet-builder'])
    expect(canSeeTab('cecchino-v4', false, allowed)).toBe(false)
    expect(canSeeTab('admin', false, ['admin'])).toBe(false)
    expect(firstAllowedPath(false, ['bet-builder'])).toBe('/bet-builder')
    expect(firstAllowedPath(false, [])).toBeNull()
  })

  it("l'amministratore vede tutto", () => {
    expect(visibleNavItems(NAV_ALL, true, [])).toHaveLength(NAV_ALL.length)
    expect(canSeeTab('admin', true, [])).toBe(true)
  })
})
