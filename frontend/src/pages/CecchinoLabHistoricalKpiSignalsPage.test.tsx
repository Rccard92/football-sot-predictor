/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CecchinoLabHistoricalKpiSignalsPage } from './CecchinoLabHistoricalKpiSignalsPage'
import { CecchinoLabHistoricalRunPage } from './CecchinoLabHistoricalRunPage'
import type {
  HistoricalKpiActivationsResponse,
  HistoricalKpiSignalsSummary,
  HistoricalKpiTimelineResponse,
  HistoricalRunDashboardOverview,
} from '../lib/cecchinoLabApi'

const apiMock = vi.hoisted(() => ({
  getHistoricalKpiSignalsSummary: vi.fn(),
  getHistoricalKpiSignalsTimeline: vi.fn(),
  getHistoricalKpiSignalActivations: vi.fn(),
  getHistoricalRunDashboardOverview: vi.fn(),
  getHistoricalRunDashboardMarkets: vi.fn(),
  getHistoricalRunDashboardRatings: vi.fn(),
  getHistoricalRunDashboardPurchasability: vi.fn(),
  getHistoricalRunDashboardSignals: vi.fn(),
  getHistoricalRunDashboardBalance: vi.fn(),
  getHistoricalRunDashboardGoalIntensity: vi.fn(),
  getHistoricalRunDashboardCompetitions: vi.fn(),
  getHistoricalRunDashboardTimeline: vi.fn(),
  getHistoricalRunDashboardPatterns: vi.fn(),
  getHistoricalRunDashboardExclusions: vi.fn(),
  listHistoricalRunMatches: vi.fn(),
}))

vi.mock('../lib/cecchinoLabApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/cecchinoLabApi')>(
    '../lib/cecchinoLabApi',
  )
  return {
    ...actual,
    ...apiMock,
  }
})

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}))

function baseOverall(overrides: Partial<HistoricalKpiSignalsSummary['overall']['real']> = {}) {
  return {
    signals_count: 10,
    evaluated_count: 8,
    wins: 5,
    losses: 3,
    pending_or_unsettled: 2,
    void_or_zero_profit: 0,
    win_rate_pct: 62.5,
    average_odds_played: 1.9,
    average_odds_won: 2.1,
    average_odds_void: 1.6,
    stake_count: 8,
    profit_units: 1.2,
    roi_pct: 15.0,
    ...overrides,
  }
}

function baseSummary(overrides: Partial<HistoricalKpiSignalsSummary> = {}): HistoricalKpiSignalsSummary {
  const overall = baseOverall()
  const buckets = ['50-59', '60-69', '70-79', '80-89', '90-99', '100']
  return {
    schema_version: 'cecchino_lab_historical_kpi_signals_v1',
    generated_at: '2026-08-02T10:00:00Z',
    run: {
      run_id: 3,
      season_label: '2021/2022',
      status: 'completed',
      scope: 'full',
    },
    filters: { quote_type: 'real' },
    available_filters: {
      competitions: ['Serie A'],
      selection_keys: ['HOME', 'DRAW'],
      date_min: '2021-08-01',
      date_max: '2022-05-01',
    },
    overall: { real: overall, synthetic: null },
    by_rating_bucket: buckets.map((b) => ({
      rating_bucket: b,
      quote_type: 'real',
      status: 'ready',
      ...overall,
    })),
    heatmap: {
      rating_buckets: buckets,
      selection_keys: ['HOME', 'DRAW'],
      cells: [
        {
          rating_bucket: '70-79',
          selection_key: 'HOME',
          quote_type: 'real',
          sample_class: 'small',
          ...overall,
          average_odds: 1.9,
        },
      ],
    },
    diagnostics: {
      rows_scanned: 100,
      rating_null: 2,
      rating_below_50: 10,
      eligible_rows: 88,
      performance_real_ready: 80,
      performance_synthetic_ready: 5,
    },
    resource_profile: {
      strategy: 'sql_aggregates',
      query_count: 3,
      rows_materialized: 88,
      full_orm_entities_loaded: false,
      jsonb_payloads_loaded: false,
    },
    ...overrides,
  }
}

function baseTimeline(): HistoricalKpiTimelineResponse {
  return {
    schema_version: 'cecchino_lab_historical_kpi_signals_v1',
    generated_at: '2026-08-02T10:00:00Z',
    run: baseSummary().run,
    filters: { quote_type: 'real' },
    group_by: 'matchday',
    effective_group_by: 'date',
    grouping_fallback: 'date',
    points: [
      {
        group_key: '2021-09-15',
        group_label: '2021-09-15',
        date_from: '2021-09-15',
        date_to: '2021-09-15',
        signals_count: 4,
        evaluated_count: 4,
        wins: 2,
        losses: 2,
        win_rate_pct: 50,
        profit_units: 0.5,
        roi_pct: 12.5,
        stake_count: 4,
        cumulative_profit_units: 0.5,
        cumulative_roi_pct: 12.5,
      },
    ],
    resource_profile: {
      strategy: 'sql_aggregates',
      query_count: 1,
      rows_materialized: 4,
      full_orm_entities_loaded: false,
      jsonb_payloads_loaded: false,
    },
  }
}

function baseActivations(): HistoricalKpiActivationsResponse {
  return {
    items: [
      {
        source_snapshot_id: 1,
        lab_match_id: 10,
        competition_name: 'Serie A',
        kickoff_at: '2021-09-15T18:00:00Z',
        matchday_label: null,
        home_team: 'Home',
        away_team: 'Away',
        market_key: 'HOME',
        market_label: '1',
        rating: 72,
        rating_bucket: '70-79',
        quote_type: 'real',
        quota_book: 1.9,
        won: true,
        profit_units: 0.9,
        evaluation_status: 'settled',
        result_reason: null,
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
    filters: { quote_type: 'real' },
    resource_profile: {
      strategy: 'sql_aggregates',
      query_count: 1,
      rows_materialized: 1,
      full_orm_entities_loaded: false,
      jsonb_payloads_loaded: false,
      activations_page_size: 50,
    },
  }
}

function baseOverview(): HistoricalRunDashboardOverview {
  return {
    run: {
      run_id: 3,
      season_label: '2021/2022',
      status: 'completed',
      scope: 'full',
      scan_version: 'v1',
      bookmaker_storico: 'Bet365',
      bookmaker_today_operativo: 'Betfair',
    },
    kpis: {},
    progress: { matches_processed: 6308, matches_total: 6308, progress_pct: 100 },
    module_coverage: {
      historical_kpi: {
        observation_status: 'complete',
        coverage_pct: 100,
        complete: 1,
        partial: 0,
        unavailable: 0,
      },
    },
    is_provisional: false,
    active_eligible_sample: 4561,
  } as unknown as HistoricalRunDashboardOverview
}

function renderKpi(path = '/cecchino-lab/historical-scans/3/kpi-signals') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/cecchino-lab/historical-scans/:runId/kpi-signals"
          element={<CecchinoLabHistoricalKpiSignalsPage />}
        />
        <Route
          path="/cecchino-lab/historical-scans/:runId"
          element={<CecchinoLabHistoricalRunPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  apiMock.getHistoricalKpiSignalsSummary.mockResolvedValue(baseSummary())
  apiMock.getHistoricalKpiSignalsTimeline.mockResolvedValue(baseTimeline())
  apiMock.getHistoricalKpiSignalActivations.mockResolvedValue(baseActivations())
  apiMock.getHistoricalRunDashboardOverview.mockResolvedValue(baseOverview())
})

describe('CecchinoLabHistoricalKpiSignalsPage', () => {
  it('monta la route KPI e carica summary', async () => {
    renderKpi()
    await waitFor(() => {
      expect(screen.getByTestId('historical-kpi-page')).toBeTruthy()
    })
    expect(apiMock.getHistoricalKpiSignalsSummary).toHaveBeenCalled()
    expect(apiMock.getHistoricalKpiSignalsTimeline).toHaveBeenCalled()
    expect(apiMock.getHistoricalKpiSignalActivations).toHaveBeenCalled()
    const actArgs = apiMock.getHistoricalKpiSignalActivations.mock.calls[0]
    expect(actArgs[2]?.limit ?? 50).toBe(50)
  })

  it('default quote_type real', async () => {
    renderKpi()
    await waitFor(() => expect(apiMock.getHistoricalKpiSignalsSummary).toHaveBeenCalled())
    const filters = apiMock.getHistoricalKpiSignalsSummary.mock.calls[0][1]
    expect(filters.quote_type).toBe('real')
  })

  it('mostra ribbon, heatmap, timeline e attivazioni', async () => {
    renderKpi()
    await waitFor(() => {
      expect(screen.getByTestId('historical-kpi-ribbon')).toBeTruthy()
      expect(screen.getByTestId('historical-kpi-heatmap')).toBeTruthy()
      expect(screen.getByTestId('historical-kpi-timeline')).toBeTruthy()
      expect(screen.getByTestId('historical-kpi-activations')).toBeTruthy()
    })
  })

  it('mostra fallback giornata per data', async () => {
    renderKpi()
    await waitFor(() => {
      expect(
        screen.getByText(/giornata originale non è disponibile/i),
      ).toBeTruthy()
    })
  })

  it('errore timeline isolato non nasconde summary', async () => {
    apiMock.getHistoricalKpiSignalsTimeline.mockRejectedValue(new Error('boom'))
    renderKpi()
    await waitFor(() => {
      expect(screen.getByTestId('historical-kpi-ribbon')).toBeTruthy()
    })
    expect(screen.getByText(/timeline/i)).toBeTruthy()
  })

  it('non mostra azioni sync/rivaluta KPI', async () => {
    renderKpi()
    await waitFor(() => expect(screen.getByTestId('historical-kpi-page')).toBeTruthy())
    expect(screen.queryByText(/Sincronizza KPI/i)).toBeNull()
    expect(screen.queryByText(/Rivaluta KPI/i)).toBeNull()
  })

  it('card fasce rating presenti', async () => {
    renderKpi()
    await waitFor(() => {
      expect(screen.getByText('50-59')).toBeTruthy()
      expect(screen.getByText('100')).toBeTruthy()
    })
  })
})

describe('CecchinoLabHistoricalRunPage hub resource-safe', () => {
  it('carica solo overview al mount', async () => {
    render(
      <MemoryRouter initialEntries={['/cecchino-lab/historical-scans/3']}>
        <Routes>
          <Route
            path="/cecchino-lab/historical-scans/:runId"
            element={<CecchinoLabHistoricalRunPage />}
          />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(apiMock.getHistoricalRunDashboardOverview).toHaveBeenCalled()
    })
    expect(apiMock.getHistoricalRunDashboardMarkets).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardRatings).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardPurchasability).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardSignals).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardBalance).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardGoalIntensity).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardCompetitions).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardTimeline).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardPatterns).not.toHaveBeenCalled()
    expect(apiMock.getHistoricalRunDashboardExclusions).not.toHaveBeenCalled()
    expect(apiMock.listHistoricalRunMatches).not.toHaveBeenCalled()
    expect(screen.getByTestId('hub-kpi-card')).toBeTruthy()
  })

  it('carica un modulo solo dopo click', async () => {
    render(
      <MemoryRouter initialEntries={['/cecchino-lab/historical-scans/3']}>
        <Routes>
          <Route
            path="/cecchino-lab/historical-scans/:runId"
            element={<CecchinoLabHistoricalRunPage />}
          />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => expect(apiMock.getHistoricalRunDashboardOverview).toHaveBeenCalled())
    apiMock.getHistoricalRunDashboardMarkets.mockResolvedValue({ markets: [] })
    fireEvent.click(screen.getByRole('button', { name: /Mercati/i }))
    await waitFor(() => {
      expect(apiMock.getHistoricalRunDashboardMarkets).toHaveBeenCalledTimes(1)
    })
    expect(apiMock.getHistoricalRunDashboardSignals).not.toHaveBeenCalled()
  })
})
