/** @vitest-environment node */
import { describe, expect, it } from 'vitest'
import {
  applyResultsFiltersPatch,
  clampResultsDate,
  defaultResultsFilters,
  formatBookQuota,
  formatProfitUnits,
  formatRoiPct,
  formatScoreLine,
  mapOutcomeFilterToApi,
  mapResultsQuickFilterToApi,
  outcomeLabel,
  parseBetBuilderView,
  signedMetricTone,
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

  it('BET-RESULTS-01.3 formatProfitUnits / formatRoiPct / signedMetricTone', () => {
    expect(formatProfitUnits(3.42)).toBe('+3.42u')
    expect(formatProfitUnits(-2.15)).toBe('-2.15u')
    expect(formatProfitUnits(0)).toBe('0.00u')
    expect(formatProfitUnits(null)).toBe('N/D')
    expect(formatRoiPct(12.4)).toBe('+12.4%')
    expect(formatRoiPct(-8.6)).toBe('-8.6%')
    expect(formatRoiPct(0)).toBe('0.0%')
    expect(formatRoiPct(null)).toBe('N/D')
    expect(signedMetricTone(1)).toBe('positive')
    expect(signedMetricTone(0)).toBe('negative')
    expect(signedMetricTone(-1)).toBe('negative')
    expect(signedMetricTone(null)).toBe('neutral')
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

  it('mapOutcomeFilterToApi — solo asse outcome (won/lost)', () => {
    expect(mapOutcomeFilterToApi('lost')).toBe('lost')
    expect(mapOutcomeFilterToApi('won')).toBe('won')
    expect(mapOutcomeFilterToApi('all')).toBeUndefined()
    expect(mapOutcomeFilterToApi('live')).toBeUndefined()
    expect(mapOutcomeFilterToApi('pending')).toBeUndefined()
  })

  it('BET-RESULTS-01.2 mapResultsQuickFilterToApi split axes', () => {
    expect(mapResultsQuickFilterToApi('all')).toEqual({})
    expect(mapResultsQuickFilterToApi('pending')).toEqual({ match_status: 'upcoming' })
    expect(mapResultsQuickFilterToApi('live')).toEqual({ match_status: 'live' })
    expect(mapResultsQuickFilterToApi('won')).toEqual({ outcome: 'won' })
    expect(mapResultsQuickFilterToApi('lost')).toEqual({ outcome: 'lost' })
  })
})

describe('BET-RESULTS-01.1 applyResultsFiltersPatch', () => {
  const today = '2026-08-08'
  const base = defaultResultsFilters(today)

  it('entering pending auto-selects kickoff_asc', () => {
    const { filters, pendingSortAuto } = applyResultsFiltersPatch(
      base,
      { outcome: 'pending' },
      false,
      today,
    )
    expect(filters.outcome).toBe('pending')
    expect(filters.sort).toBe('kickoff_asc')
    expect(pendingSortAuto).toBe(true)
  })

  it('manual sort override clears auto flag', () => {
    const pending = { ...base, outcome: 'pending' as const, sort: 'kickoff_asc' as const }
    const { filters, pendingSortAuto } = applyResultsFiltersPatch(
      pending,
      { sort: 'purchasability_desc' },
      true,
      today,
    )
    expect(filters.sort).toBe('purchasability_desc')
    expect(pendingSortAuto).toBe(false)
  })

  it('leaving pending restores recent when sort was auto', () => {
    const pending = { ...base, outcome: 'pending' as const, sort: 'kickoff_asc' as const }
    const { filters, pendingSortAuto } = applyResultsFiltersPatch(
      pending,
      { outcome: 'won' },
      true,
      today,
    )
    expect(filters.outcome).toBe('won')
    expect(filters.sort).toBe('recent')
    expect(pendingSortAuto).toBe(false)
  })

  it('leaving pending to live restores recent when auto', () => {
    const pending = { ...base, outcome: 'pending' as const, sort: 'kickoff_asc' as const }
    const { filters, pendingSortAuto } = applyResultsFiltersPatch(
      pending,
      { outcome: 'live' },
      true,
      today,
    )
    expect(filters.outcome).toBe('live')
    expect(filters.sort).toBe('recent')
    expect(pendingSortAuto).toBe(false)
  })

  it('leaving pending preserves manual sort', () => {
    const pending = {
      ...base,
      outcome: 'pending' as const,
      sort: 'purchasability_desc' as const,
    }
    const { filters, pendingSortAuto } = applyResultsFiltersPatch(
      pending,
      { outcome: 'all' },
      false,
      today,
    )
    expect(filters.sort).toBe('purchasability_desc')
    expect(pendingSortAuto).toBe(false)
  })
})
