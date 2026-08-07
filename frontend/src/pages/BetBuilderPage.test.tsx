/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BetBuilderOpportunitiesResponse, BetBuilderOpportunity } from '../lib/cecchinoBetBuilderApi'
import { BetBuilderPage } from './BetBuilderPage'

const apiMock = vi.hoisted(() => ({
  fetchBetBuilderOpportunities: vi.fn(),
  todayIsoRome: vi.fn(() => '2026-08-08'),
}))

vi.mock('../lib/cecchinoBetBuilderApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/cecchinoBetBuilderApi')>(
    '../lib/cecchinoBetBuilderApi',
  )
  return {
    ...actual,
    fetchBetBuilderOpportunities: apiMock.fetchBetBuilderOpportunities,
  }
})

vi.mock('../lib/cecchinoTodayApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/cecchinoTodayApi')>(
    '../lib/cecchinoTodayApi',
  )
  return {
    ...actual,
    todayIsoRome: apiMock.todayIsoRome,
  }
})

function baseOpportunity(overrides: Partial<BetBuilderOpportunity> = {}): BetBuilderOpportunity {
  return {
    opportunity_key: 'op-1',
    fixture: {
      today_fixture_id: 16511,
      kickoff: '2026-08-08T11:00:00Z',
      country: 'Sweden',
      league: 'Division 2',
      home: { name: 'Onsala', logo: 'https://example.com/onsala.png' },
      away: { name: 'Boljan', logo: 'https://example.com/boljan.png' },
    },
    market: { market_key: 'DRAW', label: 'X' },
    origin: 'price_and_signals',
    price_value: {
      present: true,
      method: 'book_gt_cecchino_v1',
      quota_book: 4.1,
      quota_cecchino: 2.26,
      prob_book: null,
      prob_cecchino: null,
      vantaggio_prob: null,
      edge_pct: 81.42,
      score_acquisto: null,
      rating: 100,
      rating_label: 'Elite',
      status: 'ok',
    },
    signals: {
      available: true,
      present: true,
      evidence_mode: 'consensus',
      yes_count: 2,
      required_count: 4,
      available_count: 4,
      yes_columns: ['E', 'F'],
      passed: true,
    },
    purchasability_v31: {
      available: true,
      score: 86,
      class: 'Molto Alta',
      calculation_quality: 'full',
      reading_short: 'Valore elevato',
    },
    context_support: {
      available: true,
      module: 'balance_v5',
      status: 'raw_context_only',
      payload: {
        pillars: {
          f36: { index: 73.99, class_label: 'Equilibrio' },
          dominance: { index: 29.57, class_label: 'Debole' },
          draw_credibility: { index: 45.14, class_label: 'Pareggio forte' },
          gap_coherence: { index: 75.9, class_label: 'Confermato' },
        },
        gap_coherence_index: 75.9,
      },
    },
    freshness: {},
    ...overrides,
  }
}

function baseResponse(
  overrides: Partial<BetBuilderOpportunitiesResponse> = {},
): BetBuilderOpportunitiesResponse {
  const opportunities = overrides.opportunities ?? [baseOpportunity()]
  return {
    contract_version: 'cecchino_bet_builder_contract_v1',
    aggregator_version: 'cecchino_bet_builder_opportunity_aggregator_v1',
    purchasability_policy: 'v31_only',
    scan_date: '2026-08-08',
    source_revision: 'rev-1',
    source_scan_status: 'completed',
    freshness: {
      source_scan_date: '2026-08-08',
      source_scan_status: 'completed',
      max_fixture_updated_at: '2026-08-08T10:00:00Z',
    },
    summary: {
      fixtures_considered: 172,
      fixtures_eligible_total: 172,
      opportunities_total: opportunities.length,
      price_only: 1,
      signals_only: 1,
      price_and_signals: 1,
      with_purchasability_v31: opportunities.length,
      without_purchasability_v31: 0,
      by_market: {
        HOME: 1,
        DRAW: 1,
        AWAY: 0,
        ONE_X: 0,
        X_TWO: 0,
        ONE_TWO: 0,
        DRAW_PT: 1,
        OVER_1_5: 1,
        UNDER_1_5: 0,
        OVER_2_5: 0,
        UNDER_2_5: 0,
      },
    },
    opportunities,
    ...overrides,
  }
}

function renderPage(initial = '/bet-builder?date=2026-08-08') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/bet-builder" element={<BetBuilderPage />} />
        <Route path="/cecchino-today" element={<div>Today page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('BetBuilderPage', () => {
  beforeEach(() => {
    vi.useRealTimers()
    apiMock.fetchBetBuilderOpportunities.mockReset()
    apiMock.todayIsoRome.mockReturnValue('2026-08-08')
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('carica response BET-01 e mostra summary', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(baseResponse())
    renderPage()
    expect(screen.getByTestId('bet-builder-loading')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('summary-opportunities_total')).toBeTruthy())
    expect(within(screen.getByTestId('summary-fixtures_eligible_total')).getByText('172')).toBeTruthy()
    expect(within(screen.getByTestId('summary-opportunities_total')).getByText('1')).toBeTruthy()
    expect(within(screen.getByTestId('summary-price_only')).getByText('1')).toBeTruthy()
    expect(apiMock.fetchBetBuilderOpportunities).toHaveBeenCalledWith({ date: '2026-08-08' })
  })

  it('mostra market chips con count e filtra client-side', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({ opportunity_key: 'd', market: { market_key: 'DRAW', label: 'X' } }),
          baseOpportunity({
            opportunity_key: 'h',
            market: { market_key: 'HOME', label: '1' },
            purchasability_v31: { available: true, score: 50, class: 'Media' },
          }),
        ],
        summary: {
          ...baseResponse().summary,
          opportunities_total: 2,
          by_market: { ...baseResponse().summary.by_market, DRAW: 1, HOME: 1 },
        },
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-card')).toHaveLength(2))
    expect(screen.getByRole('tab', { name: 'X, 1' })).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: '1, 1' }))
    await waitFor(() => {
      const cards = screen.getAllByTestId('bet-builder-opportunity-card')
      expect(cards).toHaveLength(1)
      expect(cards[0].getAttribute('data-market')).toBe('HOME')
    })
    expect(apiMock.fetchBetBuilderOpportunities).toHaveBeenCalledTimes(1)
  })

  it('filtro origin e signal-only visibile con price_value.present=false', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'sig-only',
            origin: 'signals',
            price_value: { ...baseOpportunity().price_value, present: false },
          }),
          baseOpportunity({
            opportunity_key: 'price-only',
            origin: 'price',
            signals: { ...baseOpportunity().signals, present: false, yes_count: 0 },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-card')).toHaveLength(2))
    fireEvent.click(screen.getByRole('button', { name: 'Segnali' }))
    await waitFor(() => {
      const cards = screen.getAllByTestId('bet-builder-opportunity-card')
      expect(cards).toHaveLength(1)
      expect(cards[0].getAttribute('data-origin')).toBe('signals')
    })
    expect(screen.getByText('Nessun valore quota rilevato')).toBeTruthy()
  })

  it('ordina per Acquistabilità V3.1 desc con null in fondo', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'null-score',
            fixture: { ...baseOpportunity().fixture, home: { name: 'NullScore FC' } },
            purchasability_v31: { available: false, score: null },
          }),
          baseOpportunity({
            opportunity_key: 'mid',
            fixture: { ...baseOpportunity().fixture, home: { name: 'Mid FC' } },
            purchasability_v31: { available: true, score: 55, class: 'Media' },
          }),
          baseOpportunity({
            opportunity_key: 'top',
            fixture: { ...baseOpportunity().fixture, home: { name: 'Top FC' } },
            purchasability_v31: { available: true, score: 95, class: 'Molto Alta' },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-card')).toHaveLength(3))
    const cards = screen.getAllByTestId('bet-builder-opportunity-card')
    expect(within(cards[0]).getByText('Top FC')).toBeTruthy()
    expect(within(cards[1]).getByText('Mid FC')).toBeTruthy()
    expect(within(cards[2]).getByText('NullScore FC')).toBeTruthy()
    expect(within(cards[2]).getByText('N/D')).toBeTruthy()
  })

  it('visualizza HOME direct_single_formula, DRAW 2/4 e 4/4, X PT derived', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'home',
            market: { market_key: 'HOME', label: '1' },
            signals: {
              available: true,
              present: true,
              evidence_mode: 'direct_single_formula',
              yes_count: 1,
              required_count: 1,
              available_count: 1,
              yes_columns: ['D'],
              passed: true,
            },
            context_support: { available: false, reason: 'no_validated_context_module' },
          }),
          baseOpportunity({
            opportunity_key: 'draw24',
            market: { market_key: 'DRAW', label: 'X' },
            signals: {
              available: true,
              present: true,
              evidence_mode: 'consensus',
              yes_count: 2,
              required_count: 4,
              available_count: 4,
              yes_columns: ['E', 'F'],
              passed: true,
            },
          }),
          baseOpportunity({
            opportunity_key: 'draw44',
            market: { market_key: 'DRAW', label: 'X' },
            fixture: {
              ...baseOpportunity().fixture,
              today_fixture_id: 2,
              home: { name: 'FullYes' },
              away: { name: 'Side' },
            },
            signals: {
              available: true,
              present: true,
              evidence_mode: 'consensus',
              yes_count: 4,
              required_count: 4,
              available_count: 4,
              yes_columns: ['D', 'E', 'F', 'G'],
              passed: true,
            },
          }),
          baseOpportunity({
            opportunity_key: 'xpt',
            market: { market_key: 'DRAW_PT', label: 'X PT' },
            signals: {
              available: true,
              present: true,
              evidence_mode: 'derived_from_draw_consensus',
              yes_count: 2,
              required_count: 4,
              available_count: 4,
              yes_columns: ['E', 'F'],
              passed: true,
            },
            context_support: {
              available: false,
              module: null,
              reason: 'no_validated_context_module',
            },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-card')).toHaveLength(4))
    expect(screen.getByText('Segnale diretto')).toBeTruthy()
    expect(screen.getByText(/D · SI/)).toBeTruthy()
    expect(screen.getAllByText('2 / 4 SI').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('4 / 4 SI')).toBeTruthy()
    expect(screen.getByText('Derivato dal consenso X')).toBeTruthy()
    expect(screen.getAllByTestId('context-unavailable').length).toBeGreaterThan(0)
  })

  it('mostra Balance 4 pilastri incluso Gap Coherence', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(baseResponse())
    renderPage()
    await waitFor(() => expect(screen.getByTestId('balance-pillar-gap_coherence')).toBeTruthy())
    expect(screen.getByTestId('balance-pillar-f36').textContent).toMatch(/73\.99/)
    expect(screen.getByTestId('balance-pillar-dominance').textContent).toMatch(/29\.57/)
    expect(screen.getByTestId('balance-pillar-draw_credibility').textContent).toMatch(/45\.14/)
    expect(screen.getByTestId('balance-pillar-gap_coherence').textContent).toMatch(/75\.9/)
    expect(screen.getByTestId('balance-pillar-gap_coherence').textContent).toMatch(/Confermato/)
  })

  it('mostra Goal Intensity official e fallback', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'gi-off',
            market: { market_key: 'UNDER_1_5', label: 'Under 1.5' },
            context_support: {
              available: true,
              module: 'goal_intensity_v5',
              status: 'raw_context_only',
              payload: {
                source: 'v5_official',
                official: true,
                expected_total_goals: 2.8,
                probability_selection: 0.225,
                probability_opposite: 0.775,
                data_quality: { status: 'ok' },
                market_key: 'UNDER_1_5',
              },
            },
          }),
          baseOpportunity({
            opportunity_key: 'gi-fb',
            market: { market_key: 'OVER_1_5', label: 'Over 1.5' },
            fixture: {
              ...baseOpportunity().fixture,
              today_fixture_id: 99,
              home: { name: 'Fallback FC' },
            },
            context_support: {
              available: true,
              module: 'goal_intensity_v5',
              status: 'v4_fallback_raw_context',
              payload: {
                source: 'v4_fallback',
                official: false,
                expected_total_goals: 2.1,
                probability_selection: 0.6,
                probability_opposite: 0.4,
                market_key: 'OVER_1_5',
              },
            },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getByText('V5 ufficiale')).toBeTruthy())
    expect(screen.getByText('Fallback V4')).toBeTruthy()
    expect(screen.getByText('2.80')).toBeTruthy()
  })

  it('loading, error retry, empty state', async () => {
    apiMock.fetchBetBuilderOpportunities.mockRejectedValueOnce(new Error('boom'))
    renderPage()
    await waitFor(() => expect(screen.getByTestId('bet-builder-error')).toBeTruthy())
    apiMock.fetchBetBuilderOpportunities.mockResolvedValueOnce(
      baseResponse({ opportunities: [], summary: { ...baseResponse().summary, opportunities_total: 0 } }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Riprova' }))
    await waitFor(() => expect(screen.getByTestId('bet-builder-empty')).toBeTruthy())
    expect(screen.getByText(/Nessuna opportunity per questa giornata/i)).toBeTruthy()
  })

  it('progressive rendering con Mostra altre', async () => {
    const opportunities = Array.from({ length: 30 }, (_, i) =>
      baseOpportunity({
        opportunity_key: `op-${i}`,
        fixture: {
          ...baseOpportunity().fixture,
          today_fixture_id: i + 1,
          home: { name: `Team ${i}` },
        },
        purchasability_v31: { available: true, score: 100 - i, class: 'Alta' },
      }),
    )
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities,
        summary: { ...baseResponse().summary, opportunities_total: 30 },
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-card')).toHaveLength(24))
    fireEvent.click(screen.getByTestId('bet-builder-show-more'))
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-card')).toHaveLength(30))
  })

  it('sostituisce dati su source_revision nuova e mostra banner running', async () => {
    apiMock.fetchBetBuilderOpportunities
      .mockResolvedValueOnce(
        baseResponse({
          source_revision: 'rev-1',
          source_scan_status: 'running',
          opportunities: [
            baseOpportunity({
              opportunity_key: 'old',
              fixture: { ...baseOpportunity().fixture, home: { name: 'Old Team' } },
            }),
          ],
        }),
      )
      .mockResolvedValue(
        baseResponse({
          source_revision: 'rev-2',
          source_scan_status: 'completed',
          opportunities: [
            baseOpportunity({
              opportunity_key: 'new',
              fixture: { ...baseOpportunity().fixture, home: { name: 'New Team' } },
            }),
          ],
        }),
      )

    renderPage()
    await waitFor(() => expect(screen.getByTestId('scan-running-banner')).toBeTruthy())
    expect(screen.getByText('Old Team')).toBeTruthy()

    // soft refresh via focus
    window.dispatchEvent(new Event('focus'))
    await waitFor(() => expect(screen.getByText('New Team')).toBeTruthy())
    expect(screen.getByTestId('revision-updated-banner')).toBeTruthy()
    expect(screen.queryByText('Old Team')).toBeNull()
  })

  it('deep-link CTA verso Cecchino Today', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(baseResponse())
    renderPage()
    await waitFor(() => expect(screen.getByRole('link', { name: /Apri analisi manuale/i })).toBeTruthy())
    const link = screen.getByRole('link', { name: /Apri analisi manuale/i })
    expect(link.getAttribute('href')).toBe('/cecchino-today?date=2026-08-08&fixture=16511')
  })

  it('Acquistabilità come score /100 non probabilità', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(baseResponse())
    renderPage()
    await waitFor(() => expect(screen.getByText(/86/)).toBeTruthy())
    expect(screen.getByText(/\/ 100/)).toBeTruthy()
    expect(screen.getByText('Completa')).toBeTruthy()
    expect(screen.queryByText(/sicura/i)).toBeNull()
    expect(screen.queryByText(/probabilità/i)).toBeNull()
  })
})
