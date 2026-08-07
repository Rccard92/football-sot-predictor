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

function setupApiMocks(options?: { modelsVersion?: 'v1' | 'v2'; modelsActivations?: number }) {
  const monitoringVersion = options?.modelsVersion ?? 'v2'
  const activations = options?.modelsActivations ?? 2
  modelsMock.mockImplementation(async (params: { monitoring_version?: string }) => {
    const version = params?.monitoring_version === 'v1' ? 'v1' : 'v2'
    const act = version === 'v1' ? activations + 1 : activations
    return {
      date_from: '2026-08-01',
      date_to: '2026-08-01',
      default_model_key: 'F',
      monitoring_version: version,
      acquisition_filter: version === 'v1' ? 'all' : 'acquired',
      models: [
        {
          model_key: 'F',
          label: 'Modello F',
          short_label: 'F',
          weights: '30 / 30 / 20 / 20',
          activations: act,
          settled: act,
          won: 1,
          lost: act - 1,
          pending: 0,
          win_rate: version === 'v1' ? 33.3 : 50,
          avg_won_book_odds: 2.1,
          quota_void: version === 'v1' ? 3 : 2,
          void_margin: 0.1,
          taken_profit_indicator: version === 'v1' ? -0.3 : 0.05,
        },
      ],
    }
  })
  summaryMock.mockResolvedValue({
    filters: { monitoring_version: monitoringVersion, acquisition_filter: monitoringVersion === 'v1' ? 'all' : 'acquired' },
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
    monitoring_version: monitoringVersion,
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

  it('models-summary riceve monitoring_version v2 di default', async () => {
    renderPage()
    await waitFor(() => expect(modelsMock).toHaveBeenCalled())
    const first = modelsMock.mock.calls[0]?.[0]
    expect(first?.monitoring_version).toBe('v2')
  })

  it('switch V1 richiama models-summary con v1 e aggiorna card', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Segnali accesi: 2')).toBeTruthy())
    fireEvent.click(screen.getByTestId('monitoring-version-v1'))
    await waitFor(() => {
      const last = modelsMock.mock.calls.at(-1)?.[0]
      expect(last?.monitoring_version).toBe('v1')
    })
    await waitFor(() => expect(screen.getByText('Segnali accesi: 3')).toBeTruthy())
    expect(screen.getByTestId('models-summary-version-badge').textContent).toContain('V1')
    expect(screen.getByTestId('models-summary-cohort-label').textContent).toContain(
      'V1 Base',
    )
  })

  it('ritorno a V2 aggiorna card e badge', async () => {
    renderPage('/monitoraggio-segnali?monitoring_version=v1')
    await waitFor(() => expect(screen.getByText('Segnali accesi: 3')).toBeTruthy())
    fireEvent.click(screen.getByTestId('monitoring-version-v2'))
    await waitFor(() => {
      const last = modelsMock.mock.calls.at(-1)?.[0]
      expect(last?.monitoring_version).toBe('v2')
    })
    await waitFor(() => expect(screen.getByText('Segnali accesi: 2')).toBeTruthy())
    expect(screen.getByTestId('models-summary-version-badge').textContent).toContain('V2')
    expect(screen.getByTestId('models-summary-cohort-label').textContent).toContain(
      'V2 Confermato',
    )
    expect(screen.getByTestId('models-summary-cohort-label').textContent).toContain(
      'single-formula',
    )
  })

  it('durante switch non mostra dati modelli stale sotto nuova versione', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Segnali accesi: 2')).toBeTruthy())
    let resolveModels: ((value: unknown) => void) | undefined
    modelsMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveModels = resolve
        }),
    )
    fireEvent.click(screen.getByTestId('monitoring-version-v1'))
    expect(screen.getByTestId('models-summary-version-badge').textContent).toContain('V1')
    await waitFor(() => expect(screen.getByTestId('models-summary-loading')).toBeTruthy())
    expect(screen.queryByText('Segnali accesi: 2')).toBeNull()
    resolveModels?.({
      date_from: '2026-08-01',
      date_to: '2026-08-01',
      default_model_key: 'F',
      monitoring_version: 'v1',
      acquisition_filter: 'all',
      models: [
        {
          model_key: 'F',
          label: 'Modello F',
          short_label: 'F',
          weights: '30 / 30 / 20 / 20',
          activations: 3,
          settled: 3,
          won: 1,
          lost: 2,
          pending: 0,
          win_rate: 33.3,
          avg_won_book_odds: 2.1,
          quota_void: 3,
          void_margin: 0.1,
          taken_profit_indicator: -0.3,
        },
      ],
    })
    await waitFor(() => expect(screen.getByText('Segnali accesi: 3')).toBeTruthy())
  })

  it('modello selezionato non viene resettato al cambio versione', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Segnali accesi: 2')).toBeTruthy())
    expect(screen.getByRole('button', { name: /Win Rate/i })).toBeTruthy()
    fireEvent.click(screen.getByTestId('monitoring-version-v1'))
    await waitFor(() => expect(screen.getByText('Segnali accesi: 3')).toBeTruthy())
    const selected = screen.getByRole('button', { name: /Win Rate/i })
    expect(selected.className).toContain('ring-2')
  })

  it('label indipendente dalla versione Monitoraggio non esiste più', async () => {
    renderPage()
    await waitFor(() => expect(modelsMock).toHaveBeenCalled())
    expect(screen.queryByTestId('models-summary-independence-label')).toBeNull()
    expect(screen.queryByText(/indipendente dalla versione Monitoraggio/i)).toBeNull()
  })

  it('microcopy e badge coorte modelli corretti in V2', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('models-summary-version-badge')).toBeTruthy())
    expect(screen.getByTestId('models-summary-version-badge').textContent).toBe('V2')
    expect(screen.getByTestId('models-summary-cohort-label').textContent).toContain(
      '≥2 SI sullo stesso segno',
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

  it('refresh conserva versione da URL', async () => {
    renderPage('/monitoraggio-segnali?monitoring_version=v1')
    await waitFor(() => expect(summaryMock).toHaveBeenCalled())
    expect(screen.getByTestId('monitoring-version-v1').getAttribute('aria-checked')).toBe(
      'true',
    )
    expect(summaryMock.mock.calls.some((c) => c[0]?.monitoring_version === 'v1')).toBe(true)
    expect(modelsMock.mock.calls.some((c) => c[0]?.monitoring_version === 'v1')).toBe(true)
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
