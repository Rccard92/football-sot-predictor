/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BetBuilderResultsFixture } from '../../lib/cecchinoBetBuilderApi'
import type { AnalysisContextState } from '../../hooks/useBetBuilderResultAnalysisContext'
import { BetBuilderResultDetailDrawer } from './BetBuilderResultDetailDrawer'
import { __clearBetBuilderAnalysisContextCacheForTests } from '../../hooks/useBetBuilderResultAnalysisContext'

const hookMock = vi.hoisted(() => ({
  state: { status: 'idle' } as AnalysisContextState,
  retry: vi.fn(),
}))

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({ children, initial: _i, animate: _a, exit: _e, transition: _t, ...props }: Record<string, unknown> & { children?: React.ReactNode }) => (
      <div {...props}>{children}</div>
    ),
    button: ({ children, initial: _i, animate: _a, exit: _e, transition: _t, ...props }: Record<string, unknown> & { children?: React.ReactNode }) => (
      <button {...props}>{children}</button>
    ),
  },
  useReducedMotion: () => true,
}))

vi.mock('../../hooks/useBetBuilderResultAnalysisContext', () => ({
  useBetBuilderResultAnalysisContext: () => hookMock,
  __clearBetBuilderAnalysisContextCacheForTests: vi.fn(),
}))

vi.mock('../cecchino/CecchinoTodayKpiPanel', () => ({
  CecchinoTodayKpiPanel: ({ todayFixtureId }: { todayFixtureId?: number }) => (
    <div data-testid="mock-kpi-panel" data-fixture-id={todayFixtureId} />
  ),
}))

vi.mock('../cecchino/CecchinoBalanceV5Panel', () => ({
  CecchinoBalanceV5Panel: ({ todayFixtureId }: { todayFixtureId?: number | null }) => (
    <div data-testid="mock-balance-panel" data-fixture-id={todayFixtureId} />
  ),
}))

vi.mock('../cecchino/CecchinoGoalIntensityV5Panel', () => ({
  CecchinoGoalIntensityV5Panel: ({ todayFixtureId }: { todayFixtureId?: number | null }) => (
    <div data-testid="mock-gi-panel" data-fixture-id={todayFixtureId} />
  ),
}))

function baseItem(): BetBuilderResultsFixture {
  return {
    fixture: {
      today_fixture_id: 42,
      provider_fixture_id: 900,
      scan_date: '2026-08-19',
      kickoff: '2026-08-19T18:00:00Z',
      country: 'Iceland',
      league: '2. Deild',
      home: { name: 'Home FC', logo: null },
      away: { name: 'Away FC', logo: null },
      match_status: 'finished',
      score: { fulltime_home: 2, fulltime_away: 1, halftime_home: 1, halftime_away: 0 },
    },
    primary: {
      opportunity_key: '42:DRAW',
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
        yes_columns: ['A'],
        passed: true,
      },
      purchasability_v31: { available: true, score: 80, class: 'Buona' },
      context_support: { available: true, module: 'balance_v5', payload: {} },
      freshness: { source_scan_date: '2026-08-19' },
      prediction_outcome: 'lost',
    },
    other_opportunities: [
      {
        opportunity_key: '42:HOME',
        fixture: {} as BetBuilderResultsFixture['primary']['fixture'],
        market: { market_key: 'HOME', label: '1' },
        origin: 'signals',
        price_value: {
          present: false,
          method: 'v31',
          quota_book: null,
          quota_cecchino: 2.0,
          prob_book: null,
          prob_cecchino: null,
          vantaggio_prob: null,
          edge_pct: null,
          score_acquisto: null,
          rating: null,
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
        purchasability_v31: { available: true, score: 70 },
        context_support: { available: false },
        freshness: { source_scan_date: '2026-08-19' },
        prediction_outcome: 'won',
      },
    ],
  }
}

describe('BetBuilderResultDetailDrawer', () => {
  afterEach(() => {
    cleanup()
    hookMock.state = { status: 'idle' }
    vi.clearAllMocks()
    __clearBetBuilderAnalysisContextCacheForTests()
  })

  it('shows summary immediately when open', () => {
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={() => {}} />)
    expect(screen.getByTestId('drawer-match')).toBeTruthy()
    expect(screen.getByTestId('drawer-primary')).toBeTruthy()
    expect(screen.getByTestId('drawer-book')).toBeTruthy()
  })

  it('uses wide drawer classes on desktop breakpoint', () => {
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={() => {}} />)
    const drawer = screen.getByTestId('bet-builder-result-drawer')
    expect(drawer.className).toMatch(/md:w-\[min\(94vw,760px\)\]/)
    expect(drawer.className).toMatch(/xl:w-\[min\(90vw,920px\)\]/)
  })

  it('shows kickoff date and time in header', () => {
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={() => {}} />)
    expect(screen.getByTestId('drawer-kickoff-datetime').textContent).toBe('19/08/2026 · 20:00')
  })

  it('shows technical analysis loading skeleton', () => {
    hookMock.state = { status: 'loading' }
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={() => {}} />)
    expect(screen.getByTestId('technical-analysis-skeleton')).toBeTruthy()
  })

  it('shows technical analysis error with retry', () => {
    hookMock.state = { status: 'error', message: 'fail' }
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={() => {}} />)
    expect(screen.getByTestId('technical-analysis-error')).toBeTruthy()
    fireEvent.click(screen.getByTestId('technical-analysis-retry'))
    expect(hookMock.retry).toHaveBeenCalled()
  })

  it('renders KPI panel by default on success', () => {
    hookMock.state = {
      status: 'success',
      data: {
        contract_version: 'bet_builder_result_analysis_context_v1',
        fixture: {
          today_fixture_id: 42,
          provider_fixture_id: 900,
          competition_id: 10,
          scan_date: '2026-08-19',
          kickoff: '2026-08-19T18:00:00Z',
          country: 'Iceland',
          league: '2. Deild',
          home_team: 'Home FC',
          away_team: 'Away FC',
        },
        kpi_panel: { version: 'cecchino_kpi_v2_betfair', rows: [] },
        balance_v5: {
          status: 'available',
          version: 'v5',
          pillars: [],
          market_deviation: { status: 'available', pairs: [], reading: '—' },
        },
        fixture_identity_consistency: { status: 'consistent' },
        balance_v5_snapshot_meta: {},
        goal_intensity_v5: { status: 'available' },
        warnings: [],
      },
    }
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={() => {}} />)
    expect(screen.getByTestId('mock-kpi-panel').getAttribute('data-fixture-id')).toBe('42')
  })

  it('switches to balance and GI tabs without refetch hook', () => {
    hookMock.state = {
      status: 'success',
      data: {
        contract_version: 'bet_builder_result_analysis_context_v1',
        fixture: {
          today_fixture_id: 42,
          provider_fixture_id: 900,
          competition_id: 10,
          scan_date: '2026-08-19',
          kickoff: null,
          country: null,
          league: null,
          home_team: null,
          away_team: null,
        },
        kpi_panel: { version: 'cecchino_kpi_v2_betfair', rows: [] },
        balance_v5: {
          status: 'available',
          version: 'v5',
          pillars: [],
          market_deviation: { status: 'available', pairs: [], reading: '—' },
        },
        fixture_identity_consistency: { status: 'consistent' },
        balance_v5_snapshot_meta: {},
        goal_intensity_v5: { status: 'available' },
        warnings: [],
      },
    }
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('technical-tab-balance'))
    expect(screen.getByTestId('mock-balance-panel')).toBeTruthy()
    fireEvent.click(screen.getByTestId('technical-tab-gi'))
    expect(screen.getByTestId('mock-gi-panel')).toBeTruthy()
  })

  it('closes on overlay click and ESC', async () => {
    const onClose = vi.fn()
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('bet-builder-result-drawer-overlay'))
    expect(onClose).toHaveBeenCalled()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('expands other opportunities accordion', () => {
    render(<BetBuilderResultDetailDrawer open item={baseItem()} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('drawer-others-toggle'))
    expect(screen.getByTestId('drawer-other-row')).toBeTruthy()
  })
})
