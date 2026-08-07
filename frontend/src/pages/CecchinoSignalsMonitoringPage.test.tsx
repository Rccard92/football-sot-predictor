/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CecchinoSignalsMonitoringPage } from './CecchinoSignalsMonitoringPage'
import { SignalsActivationsTable } from '../components/cecchino/signals/SignalsActivationsTable'
import type { SignalActivationRow } from '../lib/cecchinoSignalsApi'

const summaryMock = vi.fn()
const activationsMock = vi.fn()
const modelsMock = vi.fn()

vi.mock('../lib/cecchinoSignalsApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/cecchinoSignalsApi')>(
    '../lib/cecchinoSignalsApi',
  )
  return {
    ...actual,
    getCecchinoSignalsSummary: (...args: unknown[]) => summaryMock(...args),
    getCecchinoSignalsActivations: (...args: unknown[]) => activationsMock(...args),
    getCecchinoSignalsModelsSummary: (...args: unknown[]) => modelsMock(...args),
    getSignalMinBookOddsSettings: vi.fn().mockResolvedValue({ items: [] }),
  }
})

vi.mock('../components/cecchino/signals/SignalsFormulaLegendAccordion', () => ({
  SignalsFormulaLegendAccordion: () => <div data-testid="formula-legend" />,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function emptyBucket() {
  return {
    activations: 2,
    settled: 2,
    won: 1,
    lost: 1,
    pending: 0,
    not_evaluable: 0,
    success_rate: 50,
    avg_won_book_odds: 2.1,
    quota_void: 2,
    void_margin: 0.1,
    taken_profit_indicator: 0.05,
  }
}

function setupApiMocks() {
  modelsMock.mockResolvedValue({
    date_from: '2026-08-01',
    date_to: '2026-08-01',
    default_model_key: 'F',
    models: [
      {
        model_key: 'F',
        label: 'Modello F',
        short_label: 'F',
        weights: '30 / 30 / 20 / 20',
        activations: 2,
        settled: 2,
        won: 1,
        lost: 1,
        pending: 0,
        win_rate: 50,
        avg_won_book_odds: 2.1,
        quota_void: 2,
        void_margin: 0.1,
        taken_profit_indicator: 0.05,
      },
    ],
  })
  summaryMock.mockResolvedValue({
    filters: { monitoring_version: 'v2', acquisition_filter: 'acquired' },
    overall: emptyBucket(),
    by_signal: [],
    by_column: [],
    by_signal_and_column: [],
    diagnostics: {
      date_from: '2026-08-01',
      date_to: '2026-08-01',
      today_fixtures_count: 1,
      eligible_fixtures_count: 1,
      fixtures_with_signal_matrix_count: 1,
      signal_activations_count: 2,
      current_signal_activations_count: 2,
      evaluated_count: 2,
      won: 1,
      lost: 1,
      pending: 0,
      not_evaluable: 0,
      date_filter_field_used: 'scan_date',
      warnings: [],
    },
  })
  activationsMock.mockResolvedValue({
    items: [
      {
        id: 1,
        today_fixture_id: 10,
        scan_date: '2026-08-01',
        kickoff: null,
        match: 'A vs B',
        country_name: 'IT',
        league_name: 'Serie A',
        signal_group: 'DRAW',
        signal_label: 'X',
        source_column: 'EXCEL_D',
        target_market_label: 'X',
        evaluation_status: 'won',
        evaluation_reason: null,
        ft_score: '1-1',
        ht_score: '0-0',
        quota_book: 3.4,
        quota_cecchino: 3.2,
        edge_pct: 5,
        rating: 70,
        is_current: true,
        consensus_yes_count: 2,
        consensus_available_count: 4,
        consensus_yes_columns: ['EXCEL_D', 'EXCEL_E'],
        is_acquired: true,
        acquisition_status: 'acquired_consensus',
      },
    ],
    total: 1,
    limit: 200,
    offset: 0,
    monitoring_version: 'v2',
  })
}

function renderPage(initialEntry = '/monitoraggio-segnali') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/monitoraggio-segnali" element={<CecchinoSignalsMonitoringPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CecchinoSignalsMonitoringPage — V1/V2', () => {
  beforeEach(() => {
    setupApiMocks()
  })

  it('header contiene solo il titolo senza i testi educativi rimossi', async () => {
    renderPage()
    await waitFor(() => expect(summaryMock).toHaveBeenCalled())
    expect(screen.getByRole('heading', { name: 'Monitoraggio Segnali Cecchino' })).toBeTruthy()
    expect(
      screen.queryByText(/Analisi aggregata dei segnali SI\/NO/i),
    ).toBeNull()
    expect(screen.queryByText(/Monitoraggio = segnali comprabili/i)).toBeNull()
    expect(screen.queryByText(/X PT usa quote reali dal Pannello KPI/i)).toBeNull()
  })

  it('V2 selezionata di default con label e microcopy corretti', async () => {
    renderPage()
    await waitFor(() => expect(summaryMock).toHaveBeenCalled())
    const v2 = screen.getByTestId('monitoring-version-v2')
    expect(v2.getAttribute('aria-checked')).toBe('true')
    expect(v2.textContent).toContain('V2 · Confermato')
    expect(screen.getByTestId('monitoring-version-microcopy').textContent).toContain(
      'Richiede almeno 2 conferme SI sullo stesso segno',
    )
  })

  it('V1 label e microcopy corretti al cambio', async () => {
    renderPage()
    await waitFor(() => expect(summaryMock).toHaveBeenCalled())
    fireEvent.click(screen.getByTestId('monitoring-version-v1'))
    expect(screen.getByTestId('monitoring-version-v1').getAttribute('aria-checked')).toBe('true')
    expect(screen.getByTestId('monitoring-version-v1').textContent).toContain('V1 · Base')
    expect(screen.getByTestId('monitoring-version-microcopy').textContent).toContain(
      'una sola conferma SI',
    )
  })

  it('query param aggiornato al cambio V2→V1 e API riceve monitoring_version', async () => {
    renderPage('/monitoraggio-segnali?monitoring_version=v2')
    await waitFor(() => expect(summaryMock).toHaveBeenCalled())
    fireEvent.click(screen.getByTestId('monitoring-version-v1'))
    await waitFor(() => {
      const lastSummary = summaryMock.mock.calls.at(-1)?.[0]
      expect(lastSummary?.monitoring_version).toBe('v1')
    })
    const lastAct = activationsMock.mock.calls.at(-1)?.[0]
    expect(lastAct?.monitoring_version).toBe('v1')
  })

  it('param invalido fa fallback a V2', async () => {
    renderPage('/monitoraggio-segnali?monitoring_version=v9')
    await waitFor(() => expect(summaryMock).toHaveBeenCalled())
    expect(screen.getByTestId('monitoring-version-v2').getAttribute('aria-checked')).toBe(
      'true',
    )
  })

  it('mostra loading/opacity al cambio versione', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('monitoring-cohort-panel')).toBeTruthy())
    fireEvent.click(screen.getByTestId('monitoring-version-v1'))
    expect(screen.getByTestId('monitoring-cohort-panel').getAttribute('aria-busy')).toBe('true')
  })

  it('badge versione KPI e formula V3 distinta', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('monitoring-version-badge')).toBeTruthy())
    expect(screen.getByTestId('monitoring-version-badge').textContent).toContain(
      'Monitoraggio V2',
    )
    expect(screen.getByTestId('formula-version-badge').textContent).toContain(
      'Formula corrente V3',
    )
  })

  it('accordion soglie chiuso di default e si apre senza doppio titolo', async () => {
    renderPage()
    await waitFor(() => expect(summaryMock).toHaveBeenCalled())
    const toggle = screen.getByTestId('min-book-odds-accordion-toggle')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByTestId('signal-min-book-odds-panel')).toBeNull()
    fireEvent.click(toggle)
    await waitFor(() => expect(screen.getByTestId('signal-min-book-odds-panel')).toBeTruthy())
    const accordion = screen.getByTestId('min-book-odds-accordion')
    const titles = within(accordion).getAllByText('Soglie quota book')
    // sr-only + header button label (panel hideTitle)
    expect(titles.length).toBeLessThanOrEqual(2)
  })

  it('label models-summary indipendente', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByTestId('models-summary-independence-label').textContent).toContain(
        'indipendente dalla versione Monitoraggio',
      ),
    )
  })

  it('refresh conserva versione da URL', async () => {
    renderPage('/monitoraggio-segnali?monitoring_version=v1')
    await waitFor(() => expect(summaryMock).toHaveBeenCalled())
    expect(screen.getByTestId('monitoring-version-v1').getAttribute('aria-checked')).toBe(
      'true',
    )
    expect(summaryMock.mock.calls.some((c) => c[0]?.monitoring_version === 'v1')).toBe(true)
  })
})

describe('SignalsActivationsTable — conferme', () => {
  function row(overrides: Partial<SignalActivationRow> = {}): SignalActivationRow {
    return {
      id: 1,
      today_fixture_id: 1,
      scan_date: '2026-08-01',
      kickoff: null,
      match: 'A vs B',
      country_name: null,
      league_name: 'Serie A',
      signal_group: 'DRAW',
      signal_label: 'X',
      source_column: 'EXCEL_D',
      target_market_label: 'X',
      evaluation_status: 'won',
      evaluation_reason: null,
      ft_score: '1-1',
      ht_score: null,
      quota_book: 3.2,
      quota_cecchino: 3.0,
      edge_pct: 5,
      rating: 60,
      is_current: true,
      ...overrides,
    }
  }

  it('mostra 1/4 SI conferma singola neutrale', () => {
    render(
      <MemoryRouter>
        <SignalsActivationsTable
          items={[
            row({
              consensus_yes_count: 1,
              consensus_available_count: 4,
              consensus_yes_columns: ['EXCEL_E'],
            }),
          ]}
        />
      </MemoryRouter>,
    )
    const cells = screen.getAllByTestId('confirmations-ratio')
    expect(cells[0].textContent).toMatch(/1\s*\/\s*4 SI/)
    expect(screen.getAllByText('Conferma singola').length).toBeGreaterThan(0)
  })

  it('mostra 2/4 SI per V2', () => {
    render(
      <MemoryRouter>
        <SignalsActivationsTable
          items={[
            row({
              consensus_yes_count: 2,
              consensus_available_count: 4,
              consensus_yes_columns: ['EXCEL_E', 'EXCEL_F'],
            }),
          ]}
        />
      </MemoryRouter>,
    )
    expect(screen.getAllByTestId('confirmations-ratio')[0].textContent).toMatch(/2\s*\/\s*4 SI/)
  })

  it('mostra segnale diretto HOME/AWAY', () => {
    render(
      <MemoryRouter>
        <SignalsActivationsTable
          items={[
            row({
              signal_group: 'HOME',
              signal_label: '1',
              consensus_yes_count: 1,
              consensus_available_count: 1,
              acquisition_status: 'acquired_single_formula_exempt',
            }),
          ]}
        />
      </MemoryRouter>,
    )
    expect(screen.getAllByTestId('confirmations-direct')[0].textContent).toContain(
      'Segnale diretto',
    )
    expect(screen.getAllByText('Single-formula').length).toBeGreaterThan(0)
  })
})
