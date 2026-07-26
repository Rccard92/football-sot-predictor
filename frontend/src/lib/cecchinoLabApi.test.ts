import { describe, expect, it } from 'vitest'
import {
  formatOdd,
  isOverviewEmpty,
  matchOddsColumnLabel,
  qualityBadgeClass,
  type CecchinoLabOverview,
} from './cecchinoLabApi'

describe('cecchinoLabApi helpers', () => {
  it('formatOdd hides null as dash', () => {
    expect(formatOdd(null)).toBe('—')
    expect(formatOdd(1.45)).toBe('1.45')
  })

  it('matchOddsColumnLabel uses 1/X/2', () => {
    expect(matchOddsColumnLabel('home')).toBe('1')
    expect(matchOddsColumnLabel('draw')).toBe('X')
    expect(matchOddsColumnLabel('away')).toBe('2')
  })

  it('qualityBadgeClass maps statuses', () => {
    expect(qualityBadgeClass('complete')).toBe('lab-badge-ok')
    expect(qualityBadgeClass('partial')).toBe('lab-badge-warn')
    expect(qualityBadgeClass('error')).toBe('lab-badge-err')
  })

  it('isOverviewEmpty true for empty overview', () => {
    expect(isOverviewEmpty(null)).toBe(true)
    expect(
      isOverviewEmpty({
        is_empty: true,
        competitions_count: 0,
        seasons_count: 0,
        datasets_count: 0,
        matches_total: 0,
        matches_complete: 0,
        matches_incomplete: 0,
        anomalies_total: 0,
        anomalies_errors: 0,
        anomalies_warnings: 0,
        bet365_1x2_coverage_pct: 0,
        bet365_ou25_coverage_pct: 0,
        competitions: [],
        seasons: [],
        countries: [],
        recent_imports: [],
        best_quality_datasets: [],
        worst_quality_datasets: [],
        completeness: { complete: 0, incomplete: 0, complete_pct: 0 },
      } as CecchinoLabOverview),
    ).toBe(true)
  })
})
