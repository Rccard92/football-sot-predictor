/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BetBuilderResultFixtureCard } from './BetBuilderResultFixtureCard'
import type { BetBuilderResultsFixture } from '../../lib/cecchinoBetBuilderApi'

function baseItem(overrides: Partial<BetBuilderResultsFixture> = {}): BetBuilderResultsFixture {
  return {
    fixture: {
      today_fixture_id: 1,
      provider_fixture_id: 100,
      scan_date: '2026-08-19',
      kickoff: '2026-08-19T18:00:00Z',
      country: 'Iceland',
      league: '2. Deild',
      home: { name: 'Home', logo: null },
      away: { name: 'Away', logo: null },
      match_status: 'finished',
      score: {
        goals_home: 2,
        goals_away: 1,
        fulltime_home: 2,
        fulltime_away: 1,
      },
    },
    primary: {
      opportunity_key: '1:DRAW',
      fixture: {} as BetBuilderResultsFixture['primary']['fixture'],
      market: { market_key: 'DRAW', label: 'X' },
      origin: 'price',
      price_value: {
        present: true,
        method: 'v31',
        quota_book: 2.1,
        quota_cecchino: 1.9,
        prob_book: null,
        prob_cecchino: null,
        vantaggio_prob: null,
        edge_pct: 10,
        score_acquisto: null,
        rating: 80,
        rating_label: null,
        status: null,
      },
      signals: {
        available: true,
        present: true,
        yes_count: 2,
        required_count: 2,
        available_count: 4,
        yes_columns: [],
        passed: true,
      },
      purchasability_v31: { available: true, score: 80 },
      context_support: { available: false },
      freshness: { source_scan_date: '2026-08-19' },
      prediction_outcome: 'lost',
    },
    other_opportunities: [],
    ...overrides,
  }
}

describe('BetBuilderResultFixtureCard kickoff', () => {
  it('shows date and time in Europe/Rome', () => {
    render(<BetBuilderResultFixtureCard item={baseItem()} onOpenDetail={() => {}} />)
    expect(screen.getByText('19/08/2026 · 20:00')).toBeTruthy()
  })

  it('shows fallback for null kickoff', () => {
    const item = baseItem()
    item.fixture.kickoff = null
    render(<BetBuilderResultFixtureCard item={item} onOpenDetail={() => {}} />)
    expect(screen.getByText('—')).toBeTruthy()
  })
})
