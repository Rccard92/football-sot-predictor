/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CecchinoLabHistoricalSignalsAfPage } from './CecchinoLabHistoricalSignalsAfPage'
import type {
  HistoricalSignalsAfActivationsResponse,
  HistoricalSignalsAfSummary,
} from '../lib/cecchinoLabApi'

const apiMock = vi.hoisted(() => ({
  getHistoricalSignalsAfSummary: vi.fn(),
  getHistoricalSignalsAfActivations: vi.fn(),
}))

vi.mock('../lib/cecchinoLabApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/cecchinoLabApi')>(
    '../lib/cecchinoLabApi',
  )
  return { ...actual, ...apiMock }
})

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}))

function baseSummary(): HistoricalSignalsAfSummary {
  return {
    schema_version: 'cecchino_lab_historical_signals_af_v1',
    signal_export_schema_version: 'cecchino_lab_signal_export_v1',
    generated_at: '2026-08-02T10:00:00Z',
    run: { run_id: 3, season_label: '2021/2022', status: 'completed', scope: 'full' },
    filters: { quote_type: 'real' },
    current_model_key: 'F',
    performance_granularity: 'signal_opportunity',
    models: [
      {
        model_key: 'A',
        model_short_label: 'A',
        is_current_model: false,
        opportunity_count: 10,
        active_cell_row_count: 12,
        hit_rate: 0.5,
        real_roi_pct: 5,
        synthetic_roi_pct: null,
        overlap_with_current_model_F_count: 3,
        unique_vs_current_model_F_count: 7,
        market_best: 'HOME',
      },
      {
        model_key: 'F',
        model_short_label: 'F',
        is_current_model: true,
        opportunity_count: 8,
        active_cell_row_count: 9,
        hit_rate: 0.55,
        real_roi_pct: 8,
        synthetic_roi_pct: null,
        market_best: 'OVER_2_5',
      },
    ],
    by_market: [],
    model_overlap_matrix: [
      {
        model_a: 'A',
        model_b: 'F',
        intersection_count: 3,
        union_count: 15,
        jaccard_pct: 20,
        overlap_a_pct: 30,
        overlap_b_pct: 37.5,
      },
    ],
    consensus_distribution: [],
    unique_opportunities: 18,
    active_cells: 21,
    filtered_opportunity_count: 18,
    quote_buckets: { real: 18, derived: 0 },
    concurrent_active_signals: { '1': 15, '2': 3 },
    note: 'Le celle attive non sono scommesse indipendenti.',
    resource_profile: {
      strategy: 'filtered_snapshot_load',
      query_count: 2,
      snapshots_loaded: 10,
      opportunities_materialized: 18,
      full_orm_entities_loaded: false,
      full_signals_json_returned: false,
    },
  }
}

function baseActivations(): HistoricalSignalsAfActivationsResponse {
  return {
    items: [
      {
        opportunity_id: 'run:3:snapshot:1:model:F:market:HOME',
        snapshot_id: 1,
        lab_match_id: 10,
        competition_name: 'Serie A',
        kickoff_at: '2021-09-01T18:00:00+00:00',
        home_team: 'Home',
        away_team: 'Away',
        model_key: 'F',
        market_key: 'HOME',
        market_label: '1',
        active_cell_count: 1,
        active_cells: [],
        consensus_model_count: 2,
        consensus_models: ['A', 'F'],
        quota_book: 2.1,
        is_real_book_quote: true,
        is_derived_quote: false,
        quote_type: 'real',
        won: true,
        profit_1u_real: 1.1,
        profit_1u_synthetic: null,
        evaluation_status: 'won',
        rating: 80,
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
    filters: { quote_type: 'real' },
    performance_granularity: 'signal_opportunity',
    note: 'Una riga per opportunità unica',
    resource_profile: {
      strategy: 'filtered_snapshot_load',
      query_count: 2,
      snapshots_loaded: 10,
      opportunities_materialized: 1,
      full_orm_entities_loaded: false,
      full_signals_json_returned: false,
      activations_page_size: 50,
    },
  }
}

function renderAf(path = '/cecchino-lab/historical-scans/3/signals-af') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/cecchino-lab/historical-scans/:runId/signals-af"
          element={<CecchinoLabHistoricalSignalsAfPage />}
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
  apiMock.getHistoricalSignalsAfSummary.mockResolvedValue(baseSummary())
  apiMock.getHistoricalSignalsAfActivations.mockResolvedValue(baseActivations())
})

describe('CecchinoLabHistoricalSignalsAfPage', () => {
  it('monta route autonoma e carica summary+activations', async () => {
    renderAf()
    await waitFor(() => expect(screen.getByTestId('historical-signals-af-page')).toBeTruthy())
    expect(apiMock.getHistoricalSignalsAfSummary).toHaveBeenCalled()
    expect(apiMock.getHistoricalSignalsAfActivations).toHaveBeenCalled()
    expect(screen.getByTestId('signals-af-model-cards')).toBeTruthy()
    expect(screen.getAllByText(/modello corrente/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/celle attive non sono scommesse indipendenti/i).length).toBeGreaterThan(0)
  })

  it('click modello applica filtro', async () => {
    renderAf()
    await waitFor(() => expect(screen.getByTestId('signals-af-model-row-A')).toBeTruthy())
    fireEvent.click(screen.getByTestId('signals-af-model-row-A'))
    await waitFor(() => {
      const last = apiMock.getHistoricalSignalsAfSummary.mock.calls.at(-1)?.[1]
      expect(last?.model_key).toBe('A')
    })
  })

  it('mostra dettaglio paginato', async () => {
    renderAf()
    await waitFor(() => expect(screen.getByTestId('signals-af-activations')).toBeTruthy())
    expect(screen.getByText(/Home — Away/)).toBeTruthy()
  })

  it('loading error retry', async () => {
    apiMock.getHistoricalSignalsAfSummary.mockRejectedValueOnce(new Error('fail af'))
    renderAf()
    await waitFor(() => expect(screen.getByText(/fail af/i)).toBeTruthy())
  })
})
