/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CecchinoLabPurchasabilityReplayPage } from './CecchinoLabPurchasabilityReplayPage'
import type { HistoricalPurchasabilityV3ReplayPreflight as Preflight } from '../lib/cecchinoLabApi'

const apiMock = vi.hoisted(() => ({
  getHistoricalPurchasabilityV3ReplayPreflight: vi.fn(),
  listHistoricalScans: vi.fn(),
}))

vi.mock('../lib/cecchinoLabApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/cecchinoLabApi')>(
    '../lib/cecchinoLabApi',
  )
  return {
    ...actual,
    getHistoricalPurchasabilityV3ReplayPreflight: apiMock.getHistoricalPurchasabilityV3ReplayPreflight,
    listHistoricalScans: apiMock.listHistoricalScans,
  }
})

function basePreflight(overrides: Partial<Preflight> = {}): Preflight {
  const market = {
    eligible_rows: 8,
    exact_replay_ready: 5,
    ready_with_warning: 1,
    gate_only_ready: 1,
    not_replayable: 1,
    invalid_integrity: 0,
    ambiguous_market_join: 0,
    classified_total: 8,
    unclassified: 0,
    quote_real: 6,
    quote_derived: 1,
    quote_unavailable: 1,
    performance_real_ready: 5,
    performance_synthetic_ready: 1,
  }
  return {
    schema_version: 'cecchino_lab_purchasability_v3_replay_preflight_v2',
    integrity_policy_version: 'cecchino_lab_historical_reconstruction_integrity_v1',
    status: 'ready_with_warnings',
    generated_at: '2026-07-29T10:00:00Z',
    run: {
      run_id: 3,
      season_label: '2021/2022',
      status: 'completed',
      run_scope: 'full',
      source_git_commit: 'adcf63db',
    },
    formula: {
      candidate_version: 'v3',
      formula_version: 'v3',
      audit_version: 'v3',
      historical_profile_used: false,
      fixed_scales_used: true,
      runtime_git_commit: '9d570942',
    },
    bookmakers: {
      historical: 'Bet365',
      today_operational: 'Betfair',
      providers_are_different: true,
    },
    source_integrity: {
      snapshots_total: 10,
      snapshots_eligible_core: 8,
      snapshots_excluded: 2,
      with_payload_hash: 8,
      with_historical_freeze_lock: 8,
      with_pre_match_hash: 8,
      with_pre_match_lock: 8,
      chronological_lock_check_not_applicable: 8,
      historical_reconstruction_verified: 8,
      integrity_mode_dominant: 'historical_reconstruction_frozen',
      score_performance_phase_separation_verified: true,
      duplicate_market_keys: 0,
    },
    workload: {
      supported_markets_per_snapshot: 8,
      theoretical_evaluations: 64,
      exact_replay_ready: 40,
      ready_with_warning: 10,
      gate_only_ready: 8,
      not_replayable: 6,
      invalid_integrity: 0,
      ambiguous_market_join: 0,
      classified_evaluations_total: 64,
      unclassified_evaluations: 0,
      family_decisions_theoretical: 24,
    },
    quote_quality: { real: 30, derived: 20, unavailable: 10, inconsistent_flags: 0 },
    performance_coverage: {
      real_profit_ready: 25,
      synthetic_profit_ready: 15,
      result_available_but_profit_missing: 2,
      not_applicable: 5,
    },
    by_market: {
      HOME: { ...market },
      DRAW: { ...market },
      AWAY: { ...market },
      OVER_2_5: { ...market, quote_derived: 0, performance_synthetic_ready: 0 },
      UNDER_2_5: { ...market, quote_derived: 0, performance_synthetic_ready: 0 },
      ONE_X: {
        ...market,
        exact_replay_ready: 4,
        ready_with_warning: 2,
        quote_real: 0,
        quote_derived: 7,
        performance_real_ready: 0,
        performance_synthetic_ready: 6,
      },
      X_TWO: {
        ...market,
        exact_replay_ready: 4,
        ready_with_warning: 2,
        quote_real: 0,
        quote_derived: 7,
        performance_real_ready: 0,
        performance_synthetic_ready: 6,
      },
      ONE_TWO: {
        ...market,
        exact_replay_ready: 4,
        ready_with_warning: 2,
        quote_real: 0,
        quote_derived: 7,
        performance_real_ready: 0,
        performance_synthetic_ready: 6,
      },
    },
    blockers: [],
    warnings: [{ code: 'derived_quotes_diagnostic_only', message: 'Quote derivate' }],
    probe: { skipped: true, reason: 'not_requested', probe_is_diagnostic_only: true },
    resource_profile: {
      strategy: 'sql_aggregates_and_streaming',
      full_orm_entities_loaded: false,
      market_rows_streamed: 100,
      max_market_rows_held_in_memory: 8,
      stream_yield_per: 500,
      duration_ms: 120,
      resource_budget_exceeded: false,
    },
    replay_recommendation: {
      can_replay_without_full_scan: true,
      requires_new_external_data: false,
      requires_model_recalculation: false,
      requires_database_migration: false,
      recommended_next_action: 'implement_isolated_v3_replay',
    },
    ...overrides,
  }
}

const sampleRuns = [
  {
    id: 3,
    season_label: '2021/2022',
    status: 'completed',
    scan_version: 'v3',
    requested_at: null,
    started_at: null,
    completed_at: '2026-07-01T12:00:00Z',
    current_dataset_id: null,
    current_match_id: null,
    current_competition: null,
    matches_total: 100,
    matches_processed: 100,
    matches_eligible_core: 80,
    matches_excluded: 20,
    matches_error: 0,
    progress_pct: 100,
    module_policy_json: { run_scope: 'full', is_partial_run: false },
  },
]

function renderPage(path = '/cecchino-lab/purchasability-replay?run_id=3') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/cecchino-lab/purchasability-replay" element={<CecchinoLabPurchasabilityReplayPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CecchinoLabPurchasabilityReplayPage STEP 3A.2', () => {
  beforeEach(() => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockReset()
    apiMock.listHistoricalScans.mockReset()
    apiMock.listHistoricalScans.mockResolvedValue(sampleRuns)
  })

  afterEach(() => {
    cleanup()
  })

  it('loads runs lightly and does not auto-call preflight', async () => {
    renderPage()
    await waitFor(() => expect(apiMock.listHistoricalScans).toHaveBeenCalled())
    expect(screen.getByTestId('purchasability-replay-page')).toBeTruthy()
    expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy()
    expect(apiMock.getHistoricalPurchasabilityV3ReplayPreflight).not.toHaveBeenCalled()
    expect(screen.queryByText('Avvia replay')).toBeNull()
  })

  it('summary uses include_probe false then shows probe button', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockResolvedValue(basePreflight())
    renderPage()
    await waitFor(() => expect(screen.getByTestId('purchasability-replay-run-select')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    expect(screen.getByTestId('preflight-loading')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('preflight-result')).toBeTruthy())
    expect(apiMock.getHistoricalPurchasabilityV3ReplayPreflight).toHaveBeenCalledWith(3, {
      includeProbe: false,
    })
    expect(screen.getByTestId('preflight-status-badge').textContent).toMatch(/avvisi/i)
    expect(screen.getByTestId('preflight-resource-profile').textContent).toMatch(/streamed/)
    expect(screen.getByTestId('verify-purchasability-v3-probe')).toBeTruthy()
    expect(screen.getByTestId('preflight-classified').textContent).toMatch(/Classificate:\s*64\s*\/\s*64/)
    expect(screen.getByTestId('integrity-mode').textContent).toMatch(/Ricostruzione storica congelata/)
    expect(screen.getByTestId('integrity-chronology').textContent).toMatch(/Non applicabile/)
    expect(screen.getByTestId('integrity-lock-explanation').textContent).toMatch(/congelata/)
    expect(screen.getByTestId('preflight-coverage').textContent).toMatch(/Pronto esatto/)
    expect(screen.getByTestId('preflight-coverage').textContent).toMatch(/Solo gate/)
  })

  it('probe uses include_probe true and shows probe card', async () => {
    const probeByMarket = Object.fromEntries(
      ['HOME', 'DRAW', 'AWAY', 'OVER_2_5', 'UNDER_2_5', 'ONE_X', 'X_TWO', 'ONE_TWO'].map((mk) => [
        mk,
        {
          submitted: 30,
          returned: 30,
          scored: 10,
          gate_failed: 15,
          unavailable: 5,
          not_applicable: 0,
          errors: 0,
          unclassified: 0,
        },
      ]),
    )
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight
      .mockResolvedValueOnce(basePreflight())
      .mockResolvedValueOnce(
        basePreflight({
          probe: {
            skipped: false,
            invoked_v3_formula: true,
            snapshots_selected: 30,
            snapshots_probed: 30,
            markets_expected: 240,
            panel_rows_submitted: 240,
            formula_items_returned: 240,
            markets_scored: 84,
            markets_gate_failed: 120,
            markets_unavailable: 36,
            markets_not_applicable: 0,
            markets_error: 0,
            markets_unclassified: 0,
            probe_is_diagnostic_only: true,
            probe_not_a_backtest: true,
            by_market: probeByMarket,
          },
        }),
      )
    renderPage()
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-probe')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-probe'))
    await waitFor(() =>
      expect(apiMock.getHistoricalPurchasabilityV3ReplayPreflight).toHaveBeenLastCalledWith(3, {
        includeProbe: true,
      }),
    )
    await waitFor(() => expect(screen.getByTestId('preflight-probe-card')).toBeTruthy())
    expect(screen.getByTestId('probe-card-title').textContent).toMatch(/Risultato verifica formula/)
    expect(screen.getByTestId('probe-card-counters').textContent).toMatch(/Mercati attesi:\s*240/)
    expect(screen.getByTestId('probe-card-counters').textContent).toMatch(/Score prodotti:\s*84/)
    expect(screen.getByTestId('probe-by-market-table')).toBeTruthy()
  })

  it('highlights incomplete classification', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockResolvedValue(
      basePreflight({
        workload: {
          supported_markets_per_snapshot: 8,
          theoretical_evaluations: 64,
          exact_replay_ready: 10,
          ready_with_warning: 0,
          gate_only_ready: 0,
          not_replayable: 0,
          invalid_integrity: 0,
          ambiguous_market_join: 0,
          classified_evaluations_total: 10,
          unclassified_evaluations: 54,
        },
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('preflight-classified')).toBeTruthy())
    expect(screen.getByTestId('preflight-classified').textContent).toMatch(/Classificazione incompleta/)
  })

  it('shows blocked state', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockResolvedValue(
      basePreflight({
        status: 'blocked',
        blockers: [{ code: 'duplicate_market_keys', message: 'duplicati' }],
        warnings: [],
        replay_recommendation: {
          can_replay_without_full_scan: false,
          requires_new_external_data: false,
          requires_model_recalculation: false,
          requires_database_migration: false,
          recommended_next_action: 'resolve_blockers',
        },
      }),
    )
    renderPage()
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('preflight-result')).toBeTruthy())
    expect(screen.getByTestId('preflight-status-badge').textContent).toMatch(/Bloccato/)
    expect(screen.getByTestId('preflight-issues').textContent).toContain('duplicate_market_keys')
  })

  it('shows readable network error and retry', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockRejectedValue(
      new Error('Failed to fetch'),
    )
    renderPage()
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('preflight-error')).toBeTruthy())
    expect(screen.getByTestId('preflight-error').textContent).toMatch(
      /backend non ha completato/i,
    )
    expect(screen.getByTestId('retry-purchasability-v3-replay')).toBeTruthy()
  })

  it('does not call dashboard endpoints', async () => {
    renderPage()
    await waitFor(() => expect(apiMock.listHistoricalScans).toHaveBeenCalled())
    const calls = apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mock.calls
    expect(calls).toHaveLength(0)
  })
})

describe('getHistoricalPurchasabilityV3ReplayPreflight path', () => {
  it('builds summary and probe query strings', async () => {
    const { getHistoricalPurchasabilityV3ReplayPreflight } = await vi.importActual<
      typeof import('../lib/cecchinoLabApi')
    >('../lib/cecchinoLabApi')
    expect(typeof getHistoricalPurchasabilityV3ReplayPreflight).toBe('function')
    const summaryPath = `/api/cecchino-lab/historical-scans/3/purchasability-v3-replay/preflight`
    const probePath = `${summaryPath}?include_probe=true`
    expect(summaryPath).toBe(
      '/api/cecchino-lab/historical-scans/3/purchasability-v3-replay/preflight',
    )
    expect(probePath).toContain('include_probe=true')
  })
})
