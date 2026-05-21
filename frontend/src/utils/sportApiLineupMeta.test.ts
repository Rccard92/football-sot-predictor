import { describe, expect, it } from 'vitest'
import { formatSportApiFetchedAt, getSportApiFreshnessBadge } from './sportApiLineupMeta'

describe('formatSportApiFetchedAt', () => {
  it('formats ISO to Italian datetime', () => {
    const out = formatSportApiFetchedAt('2026-05-21T14:37:10.868582+00:00')
    expect(out).toMatch(/21[./-]05[./-]2026/)
    expect(out).toMatch(/14:37/)
  })
})

describe('getSportApiFreshnessBadge', () => {
  it('returns aggiornato for recent fetch before kickoff', () => {
    const fetched = new Date(Date.now() - 30 * 60 * 1000).toISOString()
    const kickoff = new Date(Date.now() + 24 * 3600000).toISOString()
    const badge = getSportApiFreshnessBadge(fetched, kickoff)
    expect(badge?.level).toBe('aggiornato')
  })
})
