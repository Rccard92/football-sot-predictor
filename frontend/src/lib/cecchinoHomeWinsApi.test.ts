import { describe, expect, it } from 'vitest'
import { NAV_CECCHINO, NAV_ALL } from '../config/navItems'
import { availabilityBadgeLabel } from '../lib/cecchinoHomeWinsApi'

describe('Monitoraggio Segno 1 — navigazione', () => {
  it('espone la voce menu Cecchino', () => {
    const item = NAV_CECCHINO.find((n) => n.to === '/monitoraggio-segno-1')
    expect(item).toBeTruthy()
    expect(item?.label).toBe('Monitoraggio Segno 1')
    expect(item?.section).toBe('cecchino')
  })

  it('include la route in NAV_ALL', () => {
    expect(NAV_ALL.some((n) => n.to === '/monitoraggio-segno-1')).toBe(true)
  })
})

describe('cecchinoHomeWinsApi helpers', () => {
  it('mappa badge disponibilità', () => {
    expect(availabilityBadgeLabel('available')).toBe('OK')
    expect(availabilityBadgeLabel('unavailable')).toBe('N/D')
  })
})
