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
      method: 'v31_theoretical_gate_v1',
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
    aggregator_version: 'cecchino_bet_builder_opportunity_aggregator_v2',
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

  it('carica response BET-01 e mostra summary con partite con opportunity', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(baseResponse())
    renderPage()
    expect(screen.getByTestId('bet-builder-loading')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('summary-opportunities_total')).toBeTruthy())
    expect(within(screen.getByTestId('summary-fixtures_eligible_total')).getByText('172')).toBeTruthy()
    expect(within(screen.getByTestId('summary-fixtures_with_opportunity')).getByText('1')).toBeTruthy()
    expect(within(screen.getByTestId('summary-opportunities_total')).getByText('1')).toBeTruthy()
    expect(within(screen.getByTestId('summary-price_only')).getByText('1')).toBeTruthy()
    expect(apiMock.fetchBetBuilderOpportunities).toHaveBeenCalledWith({ date: '2026-08-08' })
  })

  it('raggruppa 3 opportunity stessa fixture in 1 card', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: '16511:DRAW',
            market: { market_key: 'DRAW', label: 'X' },
            purchasability_v31: { available: true, score: 86, class: 'Molto Alta' },
          }),
          baseOpportunity({
            opportunity_key: '16511:ONE_X',
            market: { market_key: 'ONE_X', label: '1X' },
            origin: 'price',
            purchasability_v31: { available: true, score: 72, class: 'Alta' },
          }),
          baseOpportunity({
            opportunity_key: '16511:OVER_2_5',
            market: { market_key: 'OVER_2_5', label: 'Over 2.5' },
            origin: 'signals',
            purchasability_v31: { available: true, score: 61, class: 'Media' },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(1))
    const card = screen.getByTestId('bet-builder-fixture-card')
    expect(card.getAttribute('data-fixture-id')).toBe('16511')
    expect(within(card).getAllByTestId('bet-builder-opportunity-row')).toHaveLength(3)
    expect(within(card).getByText('3 opportunity')).toBeTruthy()
    expect(screen.getByTestId('bet-builder-filtered-counts').textContent).toMatch(/1 partita · 3 opportunity/)
  })

  it('2 fixture → 2 card; fixture senza opportunity non compare', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: '1:DRAW',
            fixture: { ...baseOpportunity().fixture, today_fixture_id: 1, home: { name: 'Alpha' } },
          }),
          baseOpportunity({
            opportunity_key: '2:HOME',
            fixture: { ...baseOpportunity().fixture, today_fixture_id: 2, home: { name: 'Beta' } },
            market: { market_key: 'HOME', label: '1' },
          }),
        ],
        summary: { ...baseResponse().summary, fixtures_eligible_total: 54, opportunities_total: 2 },
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(2))
    expect(within(screen.getByTestId('summary-fixtures_with_opportunity')).getByText('2')).toBeTruthy()
    expect(screen.queryByText('Gamma')).toBeNull()
  })

  it('filtro market restringe opportunity interne', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'd',
            market: { market_key: 'DRAW', label: 'X' },
          }),
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
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-row')).toHaveLength(2))
    expect(screen.getByRole('tab', { name: 'X, 1' })).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: '1, 1' }))
    await waitFor(() => {
      const rows = screen.getAllByTestId('bet-builder-opportunity-row')
      expect(rows).toHaveLength(1)
      expect(rows[0].getAttribute('data-market')).toBe('HOME')
    })
    expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(1)
    expect(apiMock.fetchBetBuilderOpportunities).toHaveBeenCalledTimes(1)
  })

  it('filtro origin restringe opportunity interne; signal-only visibile', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'sig-only',
            origin: 'signals',
            market: { market_key: 'OVER_2_5', label: 'Over 2.5' },
            price_value: { ...baseOpportunity().price_value, present: false },
          }),
          baseOpportunity({
            opportunity_key: 'price-only',
            origin: 'price',
            market: { market_key: 'DRAW', label: 'X' },
            signals: { ...baseOpportunity().signals, present: false, yes_count: 0 },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-row')).toHaveLength(2))
    fireEvent.click(screen.getByRole('button', { name: 'Segnali' }))
    await waitFor(() => {
      const rows = screen.getAllByTestId('bet-builder-opportunity-row')
      expect(rows).toHaveLength(1)
      expect(rows[0].getAttribute('data-origin')).toBe('signals')
      expect(rows[0].getAttribute('data-market')).toBe('OVER_2_5')
    })
    expect(screen.getByText('Nessun valore quota rilevato')).toBeTruthy()
    expect(
      screen.queryByTestId('bet-builder-opportunity-row')?.getAttribute('data-market'),
    ).toBe('OVER_2_5')
  })

  it('price-only e price+signals restano visibili', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'price',
            origin: 'price',
            market: { market_key: 'DRAW', label: 'X' },
          }),
          baseOpportunity({
            opportunity_key: 'both',
            origin: 'price_and_signals',
            market: { market_key: 'HOME', label: '1' },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-row')).toHaveLength(2))
    expect(screen.getAllByText('QUOTA').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Quota + Segnali' }))
    await waitFor(() => {
      const rows = screen.getAllByTestId('bet-builder-opportunity-row')
      expect(rows).toHaveLength(1)
      expect(rows[0].getAttribute('data-origin')).toBe('price_and_signals')
    })
  })

  it('ordina fixture per max Acquistabilità V3.1; null in fondo', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'null-score',
            fixture: {
              ...baseOpportunity().fixture,
              today_fixture_id: 1,
              home: { name: 'NullScore FC' },
            },
            purchasability_v31: { available: false, score: null },
          }),
          baseOpportunity({
            opportunity_key: 'mid',
            fixture: {
              ...baseOpportunity().fixture,
              today_fixture_id: 2,
              home: { name: 'Mid FC' },
            },
            purchasability_v31: { available: true, score: 55, class: 'Media' },
          }),
          baseOpportunity({
            opportunity_key: 'top',
            fixture: {
              ...baseOpportunity().fixture,
              today_fixture_id: 3,
              home: { name: 'Top FC' },
            },
            purchasability_v31: { available: true, score: 95, class: 'Molto Alta' },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(3))
    const cards = screen.getAllByTestId('bet-builder-fixture-card')
    expect(within(cards[0]).getByText('Top FC')).toBeTruthy()
    expect(within(cards[1]).getByText('Mid FC')).toBeTruthy()
    expect(within(cards[2]).getByText('NullScore FC')).toBeTruthy()
    expect(within(cards[2]).getByText('N/D')).toBeTruthy()
  })

  it('opportunity interne ordinate V3.1 desc', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({
            opportunity_key: 'low',
            market: { market_key: 'AWAY', label: '2' },
            purchasability_v31: { available: true, score: 40, class: 'Bassa' },
          }),
          baseOpportunity({
            opportunity_key: 'high',
            market: { market_key: 'DRAW', label: 'X' },
            purchasability_v31: { available: true, score: 90, class: 'Molto Alta' },
          }),
          baseOpportunity({
            opportunity_key: 'mid',
            market: { market_key: 'HOME', label: '1' },
            purchasability_v31: { available: true, score: 70, class: 'Alta' },
          }),
        ],
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-opportunity-row')).toHaveLength(3))
    const rows = screen.getAllByTestId('bet-builder-opportunity-row')
    expect(rows[0].getAttribute('data-market')).toBe('DRAW')
    expect(rows[1].getAttribute('data-market')).toBe('HOME')
    expect(rows[2].getAttribute('data-market')).toBe('AWAY')
  })

  it('visualizza HOME direct, DRAW consensus, X PT derived', async () => {
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
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(2))
    expect(screen.getByText('Segnale diretto')).toBeTruthy()
    expect(screen.getByText(/D · SI/)).toBeTruthy()
    expect(screen.getByText(/Segnali 2\/4/)).toBeTruthy()
    expect(screen.getByText(/Segnali 4\/4/)).toBeTruthy()
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

  it('progressive rendering per fixture (12) senza spezzare una partita', async () => {
    const opportunities = Array.from({ length: 15 }, (_, i) =>
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
    // fixture 1 has two ops — must not be split
    opportunities.push(
      baseOpportunity({
        opportunity_key: 'op-0-b',
        fixture: {
          ...baseOpportunity().fixture,
          today_fixture_id: 1,
          home: { name: 'Team 0' },
        },
        market: { market_key: 'HOME', label: '1' },
        purchasability_v31: { available: true, score: 99, class: 'Alta' },
      }),
    )
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities,
        summary: { ...baseResponse().summary, opportunities_total: opportunities.length },
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(12))
    const first = screen.getAllByTestId('bet-builder-fixture-card')[0]
    expect(first.getAttribute('data-fixture-id')).toBe('1')
    expect(within(first).getAllByTestId('bet-builder-opportunity-row')).toHaveLength(2)
    fireEvent.click(screen.getByTestId('bet-builder-show-more'))
    await waitFor(() => expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(15))
  })

  it('auto-refresh 3→1 aggiorna card; 1→0 elimina; 0→1 aggiunge', async () => {
    const fx = baseOpportunity().fixture
    apiMock.fetchBetBuilderOpportunities
      .mockResolvedValueOnce(
        baseResponse({
          source_revision: 'rev-1',
          opportunities: [
            baseOpportunity({
              opportunity_key: '16511:a',
              market: { market_key: 'DRAW', label: 'X' },
              purchasability_v31: { available: true, score: 90 },
            }),
            baseOpportunity({
              opportunity_key: '16511:b',
              market: { market_key: 'HOME', label: '1' },
              purchasability_v31: { available: true, score: 80 },
            }),
            baseOpportunity({
              opportunity_key: '16511:c',
              market: { market_key: 'AWAY', label: '2' },
              purchasability_v31: { available: true, score: 70 },
            }),
          ],
        }),
      )
      .mockResolvedValueOnce(
        baseResponse({
          source_revision: 'rev-2',
          opportunities: [
            baseOpportunity({
              opportunity_key: '16511:a',
              market: { market_key: 'DRAW', label: 'X' },
              purchasability_v31: { available: true, score: 90 },
            }),
          ],
        }),
      )
      .mockResolvedValueOnce(
        baseResponse({
          source_revision: 'rev-3',
          opportunities: [],
          summary: { ...baseResponse().summary, opportunities_total: 0 },
        }),
      )
      .mockResolvedValue(
        baseResponse({
          source_revision: 'rev-4',
          opportunities: [
            baseOpportunity({
              opportunity_key: '99:x',
              fixture: { ...fx, today_fixture_id: 99, home: { name: 'NewArrive' } },
            }),
          ],
        }),
      )

    renderPage()
    await waitFor(() => {
      expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(1)
      expect(screen.getAllByTestId('bet-builder-opportunity-row')).toHaveLength(3)
    })

    window.dispatchEvent(new Event('focus'))
    await waitFor(() => {
      expect(screen.getAllByTestId('bet-builder-opportunity-row')).toHaveLength(1)
      expect(screen.getByTestId('revision-updated-banner')).toBeTruthy()
    })

    window.dispatchEvent(new Event('focus'))
    await waitFor(() => expect(screen.getByTestId('bet-builder-empty')).toBeTruthy())

    window.dispatchEvent(new Event('focus'))
    await waitFor(() => {
      expect(screen.getByText('NewArrive')).toBeTruthy()
      expect(screen.getAllByTestId('bet-builder-fixture-card')).toHaveLength(1)
    })
  })

  it('deep-link CTA unica per fixture', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(
      baseResponse({
        opportunities: [
          baseOpportunity({ opportunity_key: 'a', market: { market_key: 'DRAW', label: 'X' } }),
          baseOpportunity({ opportunity_key: 'b', market: { market_key: 'HOME', label: '1' } }),
        ],
      }),
    )
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: /Apri analisi manuale/i })).toHaveLength(1),
    )
    const link = screen.getByRole('link', { name: /Apri analisi manuale/i })
    expect(link.getAttribute('href')).toBe('/cecchino-today?date=2026-08-08&fixture=16511')
  })

  it('Acquistabilità come score /100 non probabilità; nessun fixture score', async () => {
    apiMock.fetchBetBuilderOpportunities.mockResolvedValue(baseResponse())
    renderPage()
    await waitFor(() => expect(screen.getByText(/86/)).toBeTruthy())
    expect(screen.getByText(/\/ 100/)).toBeTruthy()
    expect(screen.queryByText(/fixture score/i)).toBeNull()
    expect(screen.queryByText(/sicura/i)).toBeNull()
    expect(screen.queryByText(/probabilità di vincita/i)).toBeNull()
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

    window.dispatchEvent(new Event('focus'))
    await waitFor(() => expect(screen.getByText('New Team')).toBeTruthy())
    expect(screen.getByTestId('revision-updated-banner')).toBeTruthy()
    expect(screen.queryByText('Old Team')).toBeNull()
  })
})
