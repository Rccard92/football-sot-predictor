/** @vitest-environment node */
import { describe, expect, it } from 'vitest'
import {
  clampResultsDate,
  formatBookQuota,
  formatScoreLine,
  mapOutcomeFilterToApi,
  outcomeLabel,
  parseBetBuilderView,
} from './betBuilderResultsUtils'
import { BET_BUILDER_RESULTS_START_DATE } from '../../lib/cecchinoBetBuilderApi'

describe('betBuilderResultsUtils', () => {
  it('parseBetBuilderView defaults to pre-match', () => {
    expect(parseBetBuilderView(null)).toBe('pre-match')
    expect(parseBetBuilderView('results')).toBe('results')
    expect(parseBetBuilderView('pre-match')).toBe('pre-match')
  })

  it('clampResultsDate blocks before start', () => {
    expect(clampResultsDate('2026-08-07', '2026-08-10')).toBe(BET_BUILDER_RESULTS_START_DATE)
    expect(clampResultsDate('2026-08-09', '2026-08-10')).toBe('2026-08-09')
  })

  it('formatBookQuota N/D', () => {
    expect(formatBookQuota(null)).toBe('N/D')
    expect(formatBookQuota(4.1)).toBe('4.10')
  })

  it('outcome labels', () => {
    expect(outcomeLabel('won')).toBe('Vinta')
    expect(outcomeLabel('lost')).toBe('Persa')
    expect(outcomeLabel('pending')).toBe('In attesa')
  })

  it('formatScoreLine', () => {
    expect(
      formatScoreLine({ fulltime_home: 2, fulltime_away: 1 }, 'finished'),
    ).toMatch(/2\s*[–-]\s*1/)
  })

  it('mapOutcomeFilterToApi', () => {
    expect(mapOutcomeFilterToApi('lost')).toBe('lost')
    expect(mapOutcomeFilterToApi('all')).toBeUndefined()
    expect(mapOutcomeFilterToApi('live')).toBeUndefined()
  })
})
