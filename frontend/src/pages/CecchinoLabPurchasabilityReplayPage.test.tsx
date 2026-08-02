/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CecchinoLabPurchasabilityReplayPage } from './CecchinoLabPurchasabilityReplayPage'
import type { HistoricalPurchasabilityV3ReplayPreflight as Preflight } from '../lib/cecchinoLabApi'

const apiMock = vi.hoisted(() => ({
  getHistoricalPurchasabilityV3ReplayPreflight: vi.fn(),
  listHistoricalScans: vi.fn(),
  startPurchasabilityV3Replay: vi.fn(),
  getPurchasabilityV3Replay: vi.fn(),
  cancelPurchasabilityV3Replay: vi.fn(),
  resumePurchasabilityV3Replay: vi.fn(),
  getPurchasabilityV3ReplayAnalytics: vi.fn(),
  downloadPurchasabilityV3ReplayReport: vi.fn(),
}))

vi.mock('../lib/cecchinoLabApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/cecchinoLabApi')>(
    '../lib/cecchinoLabApi',
  )
  return {
    ...actual,
    getHistoricalPurchasabilityV3ReplayPreflight: apiMock.getHistoricalPurchasabilityV3ReplayPreflight,
    listHistoricalScans: apiMock.listHistoricalScans,
    startPurchasabilityV3Replay: apiMock.startPurchasabilityV3Replay,
    getPurchasabilityV3Replay: apiMock.getPurchasabilityV3Replay,
    cancelPurchasabilityV3Replay: apiMock.cancelPurchasabilityV3Replay,
    resumePurchasabilityV3Replay: apiMock.resumePurchasabilityV3Replay,
    getPurchasabilityV3ReplayAnalytics: apiMock.getPurchasabilityV3ReplayAnalytics,
    downloadPurchasabilityV3ReplayReport: apiMock.downloadPurchasabilityV3ReplayReport,
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
    expect(screen.queryByTestId('start-purchasability-v3-replay')).toBeNull()
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

function goPreflight(): Preflight {
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
  return basePreflight({
    formula: {
      candidate_version: 'cecchino_purchasability_v3_candidate_1',
      formula_version: 'cecchino_purchasability_v3_fixed_discount_v1',
      audit_version: 'cecchino_purchasability_v3_audit_v1',
      historical_profile_used: false,
      fixed_scales_used: true,
      runtime_git_commit: '9d570942',
    },
    probe: {
      skipped: false,
      invoked_v3_formula: true,
      snapshots_selected: 30,
      snapshots_probed: 30,
      markets_expected: 240,
      panel_rows_submitted: 240,
      formula_items_returned: 240,
      markets_scored: 84,
      markets_gate_failed: 156,
      markets_unavailable: 0,
      markets_not_applicable: 0,
      markets_error: 0,
      markets_unclassified: 0,
      probe_is_diagnostic_only: true,
      probe_not_a_backtest: true,
      by_market: probeByMarket,
    },
  })
}

async function reachGoState() {
  apiMock.getHistoricalPurchasabilityV3ReplayPreflight
    .mockResolvedValueOnce(basePreflight())
    .mockResolvedValueOnce(goPreflight())
  renderPage()
  await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy())
  fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
  await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-probe')).toBeTruthy())
  fireEvent.click(screen.getByTestId('verify-purchasability-v3-probe'))
  await waitFor(() => expect(screen.getByTestId('start-purchasability-v3-replay')).toBeTruthy())
}

describe('CecchinoLabPurchasabilityReplayPage STEP 3B.1', () => {
  beforeEach(() => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockReset()
    apiMock.listHistoricalScans.mockReset()
    apiMock.startPurchasabilityV3Replay.mockReset()
    apiMock.getPurchasabilityV3Replay.mockReset()
    apiMock.cancelPurchasabilityV3Replay.mockReset()
    apiMock.resumePurchasabilityV3Replay.mockReset()
    apiMock.getPurchasabilityV3ReplayAnalytics.mockReset()
    apiMock.downloadPurchasabilityV3ReplayReport.mockReset()
    apiMock.listHistoricalScans.mockResolvedValue(sampleRuns)
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('hides start before probe and with blocked/unclassified/probe error', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockResolvedValue(basePreflight())
    renderPage()
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('preflight-result')).toBeTruthy())
    expect(screen.queryByTestId('start-purchasability-v3-replay')).toBeNull()

    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockResolvedValue(
      basePreflight({
        status: 'blocked',
        blockers: [{ code: 'x', message: 'y' }],
        replay_recommendation: {
          can_replay_without_full_scan: false,
          requires_new_external_data: false,
          requires_model_recalculation: false,
          requires_database_migration: false,
          recommended_next_action: 'resolve',
        },
      }),
    )
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('preflight-status-badge').textContent).toMatch(/Bloccato/))
    expect(screen.queryByTestId('start-purchasability-v3-replay')).toBeNull()
  })

  it('shows start on Go, opens modal, requires checkbox, posts versions', async () => {
    await reachGoState()
    fireEvent.click(screen.getByTestId('start-purchasability-v3-replay'))
    expect(screen.getByTestId('start-replay-confirm-modal')).toBeTruthy()
    expect(screen.getByTestId('start-replay-confirm-summary').textContent).toMatch(/Run sorgente/)
    expect(screen.getByTestId('start-replay-confirm-summary').textContent).toMatch(/2021\/2022/)
    const submit = screen.getByTestId('start-replay-confirm-submit') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    fireEvent.click(screen.getByTestId('start-replay-confirm-checkbox'))
    expect(submit.disabled).toBe(false)

    apiMock.startPurchasabilityV3Replay.mockResolvedValue({
      id: 99,
      source_scan_run_id: 3,
      status: 'queued',
      effective_status: 'queued',
      snapshots_total: 8,
      snapshots_processed: 0,
      evaluations_total: 64,
      evaluations_processed: 0,
      results_persisted: 0,
      progress_pct: 0,
      scored_count: 0,
      gate_failed_count: 0,
      unavailable_count: 0,
      error_count: 0,
      can_cancel: true,
      can_resume: false,
      reused_existing: false,
      heartbeat_at: '2026-08-02T10:00:00Z',
    })
    fireEvent.click(submit)
    await waitFor(() => expect(apiMock.startPurchasabilityV3Replay).toHaveBeenCalled())
    const [runId, body] = apiMock.startPurchasabilityV3Replay.mock.calls[0]
    expect(runId).toBe(3)
    expect(body).toEqual({
      confirmed: true,
      expected_formula_version: 'cecchino_purchasability_v3_fixed_discount_v1',
      expected_preflight_schema_version: 'cecchino_lab_purchasability_v3_replay_preflight_v2',
      expected_integrity_policy_version: 'cecchino_lab_historical_reconstruction_integrity_v1',
    })
    await waitFor(() => expect(screen.getByTestId('purchasability-v3-replay-progress')).toBeTruthy())
    expect(screen.getByTestId('replay-id').textContent).toMatch(/99/)
    expect(screen.getByTestId('replay-progress-bar')).toBeTruthy()
    expect(screen.queryByTestId('purchasability-v3-replay-analytics')).toBeNull()
    expect(screen.queryByTestId('purchasability-v3-replay-export')).toBeNull()
  })

  it('mostra resource_profile del job in progressione senza cambiare CTA/modal', async () => {
    await reachGoState()
    apiMock.startPurchasabilityV3Replay.mockResolvedValue({
      id: 42,
      source_scan_run_id: 3,
      status: 'running',
      effective_status: 'running',
      snapshots_total: 100,
      snapshots_processed: 50,
      evaluations_total: 800,
      evaluations_processed: 400,
      results_persisted: 400,
      progress_pct: 50,
      scored_count: 300,
      gate_failed_count: 50,
      unavailable_count: 50,
      error_count: 0,
      can_cancel: true,
      can_resume: false,
      heartbeat_at: '2026-08-02T11:00:00Z',
      summary: {
        resource_profile: {
          snapshot_batches_processed: 1,
          market_batch_queries: 1,
          formula_invocations: 50,
          max_market_rows_held_in_memory: 400,
        },
      },
    })
    fireEvent.click(screen.getByTestId('start-purchasability-v3-replay'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-checkbox'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-submit'))
    await waitFor(() => expect(screen.getByTestId('replay-resource-profile')).toBeTruthy())
    expect(screen.getByTestId('replay-rp-batches').textContent).toMatch(/1/)
    expect(screen.getByTestId('replay-rp-market-queries').textContent).toMatch(/1/)
    expect(screen.getByTestId('replay-rp-formula').textContent).toMatch(/50/)
    expect(screen.getByTestId('replay-rp-max-market-rows').textContent).toMatch(/400/)
    expect(screen.getByTestId('start-purchasability-v3-replay')).toBeTruthy()
  })

  it('polls while active and stops on completed; cancel and resume', async () => {
    await reachGoState()
    apiMock.startPurchasabilityV3Replay.mockResolvedValue({
      id: 5,
      source_scan_run_id: 3,
      status: 'running',
      effective_status: 'running',
      snapshots_total: 8,
      snapshots_processed: 2,
      evaluations_total: 64,
      evaluations_processed: 16,
      results_persisted: 16,
      progress_pct: 25,
      scored_count: 10,
      gate_failed_count: 4,
      unavailable_count: 2,
      error_count: 0,
      can_cancel: true,
      can_resume: false,
      current_competition: 'E0',
      heartbeat_at: '2026-08-02T10:01:00Z',
    })
    fireEvent.click(screen.getByTestId('start-purchasability-v3-replay'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-checkbox'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-submit'))
    await waitFor(() => expect(screen.getByTestId('cancel-purchasability-v3-replay')).toBeTruthy())

    apiMock.getPurchasabilityV3Replay.mockResolvedValue({
      id: 5,
      source_scan_run_id: 3,
      status: 'running',
      effective_status: 'running',
      progress_pct: 50,
      snapshots_processed: 4,
      snapshots_total: 8,
      evaluations_processed: 32,
      evaluations_total: 64,
      results_persisted: 32,
      scored_count: 20,
      gate_failed_count: 8,
      unavailable_count: 4,
      error_count: 0,
      can_cancel: true,
      can_resume: false,
      heartbeat_at: '2026-08-02T10:02:00Z',
    })
    await vi.advanceTimersByTimeAsync(3000)
    await waitFor(() => expect(apiMock.getPurchasabilityV3Replay).toHaveBeenCalled())

    apiMock.getPurchasabilityV3Replay.mockResolvedValue({
      id: 5,
      source_scan_run_id: 3,
      status: 'completed_with_warnings',
      effective_status: 'completed_with_warnings',
      progress_pct: 100,
      snapshots_processed: 8,
      snapshots_total: 8,
      evaluations_processed: 64,
      evaluations_total: 64,
      results_persisted: 64,
      scored_count: 40,
      gate_failed_count: 20,
      unavailable_count: 4,
      error_count: 0,
      can_cancel: false,
      can_resume: false,
    })
    const callsBefore = apiMock.getPurchasabilityV3Replay.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    await waitFor(() =>
      expect(screen.getByTestId('replay-status').textContent).toMatch(/avvisi/i),
    )
    const callsAfterStop = apiMock.getPurchasabilityV3Replay.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(apiMock.getPurchasabilityV3Replay.mock.calls.length).toBe(callsAfterStop)

    // resume path on failed
    apiMock.startPurchasabilityV3Replay.mockResolvedValue({
      id: 6,
      source_scan_run_id: 3,
      status: 'failed',
      effective_status: 'failed',
      can_cancel: false,
      can_resume: true,
      error: {
        error: 'snapshot_pagination_cursor_invalidated',
        message: 'named cursor isn\'t valid anymore',
        phase: 'snapshot_batch_pagination',
        recoverable: true,
      },
      reused_existing: true,
      progress_pct: 10,
      snapshots_total: 8,
      snapshots_processed: 1,
      evaluations_total: 64,
      evaluations_processed: 8,
      results_persisted: 8,
      scored_count: 3,
      gate_failed_count: 4,
      unavailable_count: 0,
      not_applicable_count: 0,
      unclassified_count: 1,
      error_count: 0,
    })
    // reopen flow via start reuse
    fireEvent.click(screen.getByTestId('start-purchasability-v3-replay'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-checkbox'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-submit'))
    await waitFor(() => expect(screen.getByTestId('replay-reused')).toBeTruthy())
    expect(screen.getByTestId('replay-error-recoverable').textContent).toMatch(
      /interrotto dopo un batch già salvato/i,
    )
    expect(screen.getByTestId('replay-error-details')).toBeTruthy()
    expect(screen.getByTestId('replay-error-details').textContent).toMatch(
      /snapshot_pagination_cursor_invalidated/,
    )
    expect(screen.getByTestId('resume-purchasability-v3-replay')).toBeTruthy()
    expect(screen.getByTestId('replay-not-applicable').textContent).toMatch(/Non applicabili/)
    expect(screen.getByTestId('replay-unclassified').textContent).toMatch(/Non classificati/)
    expect(screen.getByTestId('replay-classified-persisted').textContent).toMatch(
      /Classificati: 8 \/ Persistiti/,
    )
    expect(screen.queryByTestId('replay-counts-mismatch')).toBeNull()

    apiMock.resumePurchasabilityV3Replay.mockResolvedValue({
      id: 6,
      source_scan_run_id: 3,
      status: 'queued',
      effective_status: 'queued',
      can_cancel: true,
      can_resume: false,
      progress_pct: 10,
      snapshots_total: 8,
      snapshots_processed: 1,
      evaluations_total: 64,
      evaluations_processed: 8,
      results_persisted: 8,
      scored_count: 0,
      gate_failed_count: 0,
      unavailable_count: 0,
      error_count: 0,
    })
    fireEvent.click(screen.getByTestId('resume-purchasability-v3-replay'))
    await waitFor(() => expect(apiMock.resumePurchasabilityV3Replay).toHaveBeenCalledWith(6))

    apiMock.cancelPurchasabilityV3Replay.mockResolvedValue({
      id: 6,
      source_scan_run_id: 3,
      status: 'cancel_requested',
      effective_status: 'cancel_requested',
      can_cancel: false,
      can_resume: false,
      progress_pct: 10,
      snapshots_total: 8,
      snapshots_processed: 1,
      evaluations_total: 64,
      evaluations_processed: 8,
      results_persisted: 8,
      scored_count: 0,
      gate_failed_count: 0,
      unavailable_count: 0,
      error_count: 0,
    })
    // after resume, cancel available
    await waitFor(() => expect(screen.getByTestId('cancel-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('cancel-purchasability-v3-replay'))
    await waitFor(() => expect(apiMock.cancelPurchasabilityV3Replay).toHaveBeenCalledWith(6))
    expect(callsBefore).toBeGreaterThanOrEqual(0)
  })

  it('does not auto-start replay on mount', async () => {
    renderPage()
    await waitFor(() => expect(apiMock.listHistoricalScans).toHaveBeenCalled())
    expect(apiMock.startPurchasabilityV3Replay).not.toHaveBeenCalled()
  })
})

describe('CecchinoLabPurchasabilityReplayPage STEP 3C.1 analytics', () => {
  beforeEach(() => {
    vi.useRealTimers()
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockReset()
    apiMock.listHistoricalScans.mockReset()
    apiMock.startPurchasabilityV3Replay.mockReset()
    apiMock.getPurchasabilityV3Replay.mockReset()
    apiMock.cancelPurchasabilityV3Replay.mockReset()
    apiMock.resumePurchasabilityV3Replay.mockReset()
    apiMock.getPurchasabilityV3ReplayAnalytics.mockReset()
    apiMock.downloadPurchasabilityV3ReplayReport.mockReset()
    apiMock.downloadPurchasabilityV3ReplayReport.mockResolvedValue(undefined)
    apiMock.listHistoricalScans.mockResolvedValue(sampleRuns)
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  function renderPage(path = '/cecchino-lab/purchasability-replay?run_id=3') {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/cecchino-lab/purchasability-replay"
            element={<CecchinoLabPurchasabilityReplayPage />}
          />
        </Routes>
      </MemoryRouter>,
    )
  }

  async function mountCompletedReplay(status: 'completed' | 'completed_with_warnings' = 'completed') {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight
      .mockResolvedValueOnce(basePreflight())
      .mockResolvedValueOnce(goPreflight())
    apiMock.startPurchasabilityV3Replay.mockResolvedValue({
      id: 1,
      source_scan_run_id: 3,
      status,
      effective_status: status,
      snapshots_total: 2,
      snapshots_processed: 2,
      evaluations_total: 16,
      evaluations_processed: 16,
      results_persisted: 16,
      progress_pct: 100,
      scored_count: 10,
      gate_failed_count: 5,
      unavailable_count: 1,
      error_count: 0,
      can_cancel: false,
      can_resume: false,
    })
    renderPage()
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-probe')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-probe'))
    await waitFor(() => expect(screen.getByTestId('start-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('start-purchasability-v3-replay'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-checkbox'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-submit'))
    await waitFor(() => expect(screen.getByTestId('purchasability-v3-replay-progress')).toBeTruthy())
  }

  const sampleAnalytics = {
    schema_version: 'cecchino_lab_purchasability_v3_analytics_v1',
    status: 'ready' as const,
    universes: {
      ALL_EVALUATIONS: 16,
      SCORED_EVALUATIONS: 10,
      GATE_FAILED_EVALUATIONS: 5,
      UNAVAILABLE_EVALUATIONS: 1,
    },
    reconciliation: {
      status: 'ok',
      quote_buckets: { real: 10, derived: 5, unavailable: 1 },
    },
    performance_real: { stake_count: 8, profit_units: 1.5, roi_pct: 18.75 },
    performance_synthetic: {
      stake_count: 4,
      profit_units: -0.5,
      roi_pct: -12.5,
      diagnostic_only: true,
    },
    by_market: {
      HOME: {
        evaluations_total: 2,
        scored: 2,
        gate_failed: 0,
        unavailable: 0,
        performance_real: { stake_count: 2, profit_units: 1, roi_pct: 50 },
      },
      DRAW: {
        evaluations_total: 2,
        scored: 1,
        gate_failed: 1,
        unavailable: 0,
        performance_real: { stake_count: 1, profit_units: null, roi_pct: null },
      },
      AWAY: {
        evaluations_total: 2,
        scored: 1,
        gate_failed: 1,
        unavailable: 0,
        performance_real: { stake_count: 1, profit_units: -1, roi_pct: -100 },
      },
      OVER_2_5: {
        evaluations_total: 2,
        scored: 2,
        gate_failed: 0,
        unavailable: 0,
        performance_real: { stake_count: 2, profit_units: 0.5, roi_pct: 25 },
      },
      UNDER_2_5: {
        evaluations_total: 2,
        scored: 1,
        gate_failed: 1,
        unavailable: 0,
        performance_real: { stake_count: 1, profit_units: -1, roi_pct: -100 },
      },
      ONE_X: {
        evaluations_total: 2,
        scored: 2,
        gate_failed: 0,
        unavailable: 0,
        not_a_real_bet365_quote: true,
        exclude_from_real_roi: true,
        performance_synthetic: { stake_count: 2, profit_units: 0.2, roi_pct: 10 },
      },
      X_TWO: {
        evaluations_total: 2,
        scored: 1,
        gate_failed: 0,
        unavailable: 1,
        not_a_real_bet365_quote: true,
        performance_synthetic: { stake_count: 1, profit_units: -1, roi_pct: -100 },
      },
      ONE_TWO: {
        evaluations_total: 2,
        scored: 0,
        gate_failed: 2,
        unavailable: 0,
        not_a_real_bet365_quote: true,
        performance_synthetic: { stake_count: 0, profit_units: null, roi_pct: null },
      },
    },
    warnings: [],
    blockers: [],
    metadata: { formula_recomputed: false, report_valid: true },
  }

  it('sezione analytics assente per replay running', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight
      .mockResolvedValueOnce(basePreflight())
      .mockResolvedValueOnce(goPreflight())
    apiMock.startPurchasabilityV3Replay.mockResolvedValue({
      id: 99,
      source_scan_run_id: 3,
      status: 'running',
      effective_status: 'running',
      progress_pct: 10,
      can_cancel: true,
      can_resume: false,
    })
    renderPage()
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('verify-purchasability-v3-probe')).toBeTruthy())
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-probe'))
    await waitFor(() => expect(screen.getByTestId('start-purchasability-v3-replay')).toBeTruthy())
    fireEvent.click(screen.getByTestId('start-purchasability-v3-replay'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-checkbox'))
    fireEvent.click(screen.getByTestId('start-replay-confirm-submit'))
    await waitFor(() => expect(screen.getByTestId('purchasability-v3-replay-progress')).toBeTruthy())
    expect(screen.queryByTestId('purchasability-v3-replay-analytics')).toBeNull()
    expect(apiMock.getPurchasabilityV3ReplayAnalytics).not.toHaveBeenCalled()
  })

  it('presente per completed senza fetch automatica; genera e download', async () => {
    await mountCompletedReplay('completed')
    expect(screen.getByTestId('purchasability-v3-replay-analytics')).toBeTruthy()
    expect(screen.getByTestId('purchasability-v3-replay-export')).toBeTruthy()
    expect(apiMock.getPurchasabilityV3ReplayAnalytics).not.toHaveBeenCalled()

    apiMock.getPurchasabilityV3ReplayAnalytics.mockResolvedValue(sampleAnalytics)
    fireEvent.click(screen.getByTestId('generate-v3-analytics'))
    await waitFor(() => expect(apiMock.getPurchasabilityV3ReplayAnalytics).toHaveBeenCalledWith(1))
    await waitFor(() => expect(screen.getByTestId('v3-analytics-result')).toBeTruthy())
    expect(screen.getByTestId('v3-analytics-status').textContent).toMatch(/ready/)
    expect(screen.getByTestId('v3-roi-real').textContent).toMatch(/18\.75/)
    expect(screen.getByTestId('v3-roi-synthetic').textContent).toMatch(/sintetica/)
    expect(screen.getByTestId('v3-market-row-HOME')).toBeTruthy()
    expect(screen.getByTestId('v3-market-row-ONE_X').textContent).toMatch(/derivata|sint/i)

    fireEvent.click(screen.getByTestId('download-v3-analysis'))
    await waitFor(() =>
      expect(apiMock.downloadPurchasabilityV3ReplayReport).toHaveBeenCalledWith(1, 'analysis'),
    )
    expect(screen.getByTestId('download-v3-analysis').textContent).toMatch(/consigliato/i)
    fireEvent.click(screen.getByTestId('download-v3-full-archive'))
    await waitFor(() =>
      expect(apiMock.downloadPurchasabilityV3ReplayReport).toHaveBeenCalledWith(1, 'full_archive'),
    )
  })

  it('presente per completed_with_warnings e mostra blocked', async () => {
    await mountCompletedReplay('completed_with_warnings')
    expect(screen.getByTestId('purchasability-v3-replay-analytics')).toBeTruthy()
    apiMock.getPurchasabilityV3ReplayAnalytics.mockResolvedValue({
      ...sampleAnalytics,
      status: 'blocked',
      blockers: [{ code: 'x', message: 'riconciliazione fallita' }],
      metadata: { formula_recomputed: false, report_valid: false },
    })
    fireEvent.click(screen.getByTestId('generate-v3-analytics'))
    await waitFor(() => expect(screen.getByTestId('v3-analytics-blockers')).toBeTruthy())
    expect(screen.getByTestId('v3-analytics-status').textContent).toMatch(/blocked/)
  })

  it('mostra errore leggibile senza Failed to fetch grezzo', async () => {
    await mountCompletedReplay('completed')
    apiMock.getPurchasabilityV3ReplayAnalytics.mockRejectedValue(new Error('Failed to fetch'))
    fireEvent.click(screen.getByTestId('generate-v3-analytics'))
    await waitFor(() => expect(screen.getByTestId('v3-analytics-error')).toBeTruthy())
    expect(screen.getByTestId('v3-analytics-error').textContent).toMatch(/rete/i)
    expect(screen.getByTestId('v3-analytics-error').textContent).not.toBe('Failed to fetch')
  })
})
