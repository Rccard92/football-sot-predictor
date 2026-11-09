import { describe, expect, it } from 'vitest'
import { oddsAge } from './oddsAgeText'

describe('oddsAge', () => {
  const now = new Date('2026-11-09T15:00:00Z').getTime()

  it('quote del mattino: piu di 6 ore nel pomeriggio', () => {
    const age = oddsAge('2026-11-09T05:05:00Z', now)!
    expect(age.stale).toBe(true)
    expect(age.text).toBe('Quote lette oggi alle 06:05 (9 ore fa)')
  })

  it('quote di ieri per le partite di oggi', () => {
    const age = oddsAge('2026-11-08T05:22:00Z', now)!
    expect(age.text.startsWith('Quote lette ieri alle 06:22')).toBe(true)
    expect(age.stale).toBe(true)
  })

  it('quote fresche: nessun avviso', () => {
    const age = oddsAge('2026-11-09T12:30:00Z', now)!
    expect(age.stale).toBe(false)
    expect(age.text).toBe('Quote lette oggi alle 13:30 (2 ore fa)')
    expect(oddsAge(null, now)).toBeNull()
  })
})
