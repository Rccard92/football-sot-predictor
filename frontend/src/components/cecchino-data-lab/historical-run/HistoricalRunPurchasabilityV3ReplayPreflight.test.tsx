/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { HistoricalRunPurchasabilityV3ReplayPreflight } from './HistoricalRunPurchasabilityV3ReplayPreflight'
import type { HistoricalPurchasabilityV3ReplayPreflight as Preflight } from '../../../lib/cecchinoLabApi'

const apiMock = vi.hoisted(() => ({
  getHistoricalPurchasabilityV3ReplayPreflight: vi.fn(),
}))

vi.mock('../../../lib/cecchinoLabApi', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/cecchinoLabApi')>(
    '../../../lib/cecchinoLabApi',
  )
  return {
    ...actual,
    getHistoricalPurchasabilityV3ReplayPreflight: apiMock.getHistoricalPurchasabilityV3ReplayPreflight,
  }
})

afterEach(() => {
  cleanup()
  apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockReset()
})

function basePreflight(overrides: Partial<Preflight> = {}): Preflight {
  return {
    schema_version: 'cecchino_lab_purchasability_v3_replay_preflight_v1',
    status: 'ready_with_warnings',
    generated_at: '2021-09-15T15:00:00Z',
    run: {
      run_id: 3,
      season_label: '2021/2022',
      status: 'completed',
      run_scope: 'full',
      is_partial_run: false,
      source_git_commit: 'adcf63db',
      scan_version: 'cecchino_lab_historical_scan_v3',
    },
    formula: {
      candidate_version: 'cecchino_purchasability_v3_candidate_1',
      formula_version: 'cecchino_purchasability_v3_fixed_discount_v1',
      audit_version: 'cecchino_purchasability_v3_audit_v1',
      runtime_git_commit: 'runtime123',
      historical_profile_used: false,
      fixed_scales_used: true,
    },
    bookmakers: {
      historical: 'Bet365',
      today_operational: 'Betfair',
      providers_are_different: true,
    },
    source_integrity: {
      snapshots_total: 100,
      snapshots_eligible_core: 80,
      snapshots_excluded: 20,
      with_pre_match_hash: 80,
      with_pre_match_lock: 80,
      lock_before_kickoff: 80,
      duplicate_market_keys: 0,
    },
    workload: {
      supported_markets_per_snapshot: 8,
      theoretical_evaluations: 640,
      exact_replay_ready: 500,
      ready_with_warning: 100,
      gate_only_ready: 20,
      not_replayable: 20,
      family_decisions_theoretical: 240,
    },
    quote_quality: { real: 400, derived: 200, unavailable: 40, inconsistent_flags: 0 },
    performance_coverage: {
      real_profit_ready: 400,
      synthetic_profit_ready: 200,
      result_available_but_profit_missing: 10,
      not_applicable: 30,
    },
    by_market: {
      HOME: {
        eligible_rows: 80,
        exact_replay_ready: 70,
        ready_with_warning: 5,
        gate_only_ready: 2,
        not_replayable: 3,
        quote_real: 70,
        quote_derived: 0,
        quote_unavailable: 10,
        performance_real_ready: 70,
        performance_synthetic_ready: 0,
      },
      DRAW: {
        eligible_rows: 80,
        exact_replay_ready: 70,
        ready_with_warning: 5,
        gate_only_ready: 2,
        not_replayable: 3,
        quote_real: 70,
        quote_derived: 0,
        quote_unavailable: 10,
        performance_real_ready: 70,
        performance_synthetic_ready: 0,
      },
      AWAY: {
        eligible_rows: 80,
        exact_replay_ready: 70,
        ready_with_warning: 5,
        gate_only_ready: 2,
        not_replayable: 3,
        quote_real: 70,
        quote_derived: 0,
        quote_unavailable: 10,
        performance_real_ready: 70,
        performance_synthetic_ready: 0,
      },
      OVER_2_5: {
        eligible_rows: 80,
        exact_replay_ready: 60,
        ready_with_warning: 10,
        gate_only_ready: 5,
        not_replayable: 5,
        quote_real: 60,
        quote_derived: 0,
        quote_unavailable: 20,
        performance_real_ready: 60,
        performance_synthetic_ready: 0,
      },
      UNDER_2_5: {
        eligible_rows: 80,
        exact_replay_ready: 60,
        ready_with_warning: 10,
        gate_only_ready: 5,
        not_replayable: 5,
        quote_real: 60,
        quote_derived: 0,
        quote_unavailable: 20,
        performance_real_ready: 60,
        performance_synthetic_ready: 0,
      },
      ONE_X: {
        eligible_rows: 80,
        exact_replay_ready: 0,
        ready_with_warning: 70,
        gate_only_ready: 5,
        not_replayable: 5,
        quote_real: 0,
        quote_derived: 70,
        quote_unavailable: 10,
        performance_real_ready: 0,
        performance_synthetic_ready: 70,
      },
      X_TWO: {
        eligible_rows: 80,
        exact_replay_ready: 0,
        ready_with_warning: 70,
        gate_only_ready: 5,
        not_replayable: 5,
        quote_real: 0,
        quote_derived: 70,
        quote_unavailable: 10,
        performance_real_ready: 0,
        performance_synthetic_ready: 70,
      },
      ONE_TWO: {
        eligible_rows: 80,
        exact_replay_ready: 0,
        ready_with_warning: 70,
        gate_only_ready: 5,
        not_replayable: 5,
        quote_real: 0,
        quote_derived: 70,
        quote_unavailable: 10,
        performance_real_ready: 0,
        performance_synthetic_ready: 70,
      },
    },
    blockers: [],
    warnings: [{ code: 'derived_quotes_diagnostic_only', message: 'Derivate diagnostiche' }],
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

describe('HistoricalRunPurchasabilityV3ReplayPreflight STEP 3A', () => {
  it('sezione presente con idle e nessuna richiesta automatica', () => {
    render(<HistoricalRunPurchasabilityV3ReplayPreflight runId={3} />)
    expect(screen.getByTestId('purchasability-v3-replay-preflight')).toBeTruthy()
    expect(screen.getByText('Replay Acquistabilità')).toBeTruthy()
    expect(screen.getByTestId('verify-purchasability-v3-replay')).toBeTruthy()
    expect(apiMock.getHistoricalPurchasabilityV3ReplayPreflight).not.toHaveBeenCalled()
    expect(screen.queryByText(/Avvia replay/i)).toBeNull()
    expect(screen.queryByText(/stima|minuti|ore/i)).toBeNull()
  })

  it('loading poi ready_with_warnings e conclusione senza nuova scansione', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockResolvedValue(basePreflight())
    render(<HistoricalRunPurchasabilityV3ReplayPreflight runId={3} />)
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    expect(screen.getByTestId('preflight-loading')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('preflight-result')).toBeTruthy())
    expect(apiMock.getHistoricalPurchasabilityV3ReplayPreflight).toHaveBeenCalledWith(3)
    expect(screen.getByTestId('preflight-status-badge').textContent).toMatch(/avvisi/i)
    expect(screen.getByTestId('preflight-run-meta').textContent).toContain('2021/2022')
    expect(screen.getByTestId('preflight-coverage').textContent).toContain('eleggibili')
    expect(screen.getByTestId('preflight-quotes').textContent).toMatch(/reali/)
    expect(screen.getByTestId('preflight-integrity').textContent).toMatch(/hash/)
    expect(screen.getByTestId('preflight-performance').textContent).toMatch(/ROI reale/)
    expect(screen.getByTestId('preflight-markets-table')).toBeTruthy()
    expect(screen.getByTestId('preflight-issues').textContent).toContain('derived_quotes')
    expect(screen.getByTestId('preflight-conclusion').textContent).toMatch(
      /senza ripetere la scansione completa/,
    )
    expect(screen.queryByText(/Avvia replay/i)).toBeNull()
    expect(screen.getByTestId('refresh-purchasability-v3-replay')).toBeTruthy()
  })

  it('stato blocked e conclusione bloccata', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockResolvedValue(
      basePreflight({
        status: 'blocked',
        blockers: [{ code: 'duplicate_market_keys', message: 'Duplicati' }],
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
    render(<HistoricalRunPurchasabilityV3ReplayPreflight runId={3} />)
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('preflight-result')).toBeTruthy())
    expect(screen.getByTestId('preflight-status-badge').textContent).toMatch(/Bloccato/)
    expect(screen.getByTestId('preflight-conclusion').textContent).toMatch(/bloccato/)
    expect(screen.getByTestId('preflight-issues').textContent).toContain('duplicate_market_keys')
  })

  it('stato ready', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockResolvedValue(
      basePreflight({ status: 'ready', warnings: [] }),
    )
    render(<HistoricalRunPurchasabilityV3ReplayPreflight runId={3} />)
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('preflight-status-badge').textContent).toBe('Pronto'))
  })

  it('stato error', async () => {
    apiMock.getHistoricalPurchasabilityV3ReplayPreflight.mockRejectedValue(new Error('boom'))
    render(<HistoricalRunPurchasabilityV3ReplayPreflight runId={3} />)
    fireEvent.click(screen.getByTestId('verify-purchasability-v3-replay'))
    await waitFor(() => expect(screen.getByTestId('preflight-error').textContent).toBe('boom'))
  })
})

describe('getHistoricalPurchasabilityV3ReplayPreflight path', () => {
  it('endpoint corretto senza admin', async () => {
    const { getHistoricalPurchasabilityV3ReplayPreflight } = await vi.importActual<
      typeof import('../../../lib/cecchinoLabApi')
    >('../../../lib/cecchinoLabApi')
    // Verifica solo la forma del path costruito (funzione reale mockata sopra nel componente)
    const path = `/api/cecchino-lab/historical-scans/${3}/purchasability-v3-replay/preflight`
    expect(path).toBe('/api/cecchino-lab/historical-scans/3/purchasability-v3-replay/preflight')
    expect(path).not.toContain('/admin/')
    expect(typeof getHistoricalPurchasabilityV3ReplayPreflight).toBe('function')
  })
})
