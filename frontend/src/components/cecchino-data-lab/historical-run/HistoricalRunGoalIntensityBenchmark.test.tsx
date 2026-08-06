/** @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HistoricalRunGoalIntensityBenchmark } from './HistoricalRunGoalIntensityBenchmark'

vi.mock('../../../lib/cecchinoLabApi', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/cecchinoLabApi')>(
    '../../../lib/cecchinoLabApi',
  )
  return {
    ...actual,
    listGoalIntensityBenchmarkJobs: vi.fn().mockResolvedValue({ jobs: [] }),
    goalIntensityBenchmarkPreflight: vi.fn(),
    startGoalIntensityBenchmarkJob: vi.fn(),
    getGoalIntensityBenchmarkJob: vi.fn(),
    cancelGoalIntensityBenchmarkJob: vi.fn(),
    resumeGoalIntensityBenchmarkJob: vi.fn(),
    downloadGoalIntensityBenchmarkExport: vi.fn(),
  }
})

import * as api from '../../../lib/cecchinoLabApi'

afterEach(() => cleanup())

describe('HistoricalRunGoalIntensityBenchmark', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listGoalIntensityBenchmarkJobs).mockResolvedValue({ jobs: [] })
  })

  it('mostra sezione disabilitata se run non completed', () => {
    render(
      <HistoricalRunGoalIntensityBenchmark
        runId={1}
        runStatus="running"
        seasonLabel="2021/22"
        snapshotsTotal={100}
      />,
    )
    expect(screen.getByTestId('historical-run-gi-benchmark')).toBeTruthy()
    expect(screen.getByText(/solo per run completed/i)).toBeTruthy()
  })

  it('esegue preflight e mostra independence badge', async () => {
    vi.mocked(api.goalIntensityBenchmarkPreflight).mockResolvedValue({
      status: 'preview',
      run: { id: 1, status: 'completed', season: '2021/22', snapshots_found: 10 },
      bundle: {
        id: 9,
        version: api.GI_HISTORICAL_BENCHMARK_BUNDLE_VERSION,
        status: 'frozen_external_benchmark_candidate',
        is_active: false,
        definition_hash: 'abc',
      },
      independence: {
        status: 'external_independent',
        scientific_label: 'external_validation',
        overlap_count: 0,
        overlap_pct: 0,
      },
      availability: {
        v4_rebuildable: 5,
        v5_features_rebuildable: 8,
        paired_complete_estimate: 5,
        blocked: false,
        missing_by_reason: { missing_persisted_v4_expected_goals: 5 },
      },
      pilot: { requested: 300, selected: 10, selection_hash: 'sel' },
      checks: {
        external_api_calls: 0,
        full_scan_required: false,
        base_run_writes: 0,
        bundle_refit: false,
        result_used_in_prediction: false,
      },
      pilot_allowed: true,
      blocking_reasons: [],
    })

    render(
      <HistoricalRunGoalIntensityBenchmark
        runId={1}
        runStatus="completed"
        seasonLabel="2021/22"
        snapshotsTotal={10}
      />,
    )

    fireEvent.click(screen.getByTestId('gi-bench-preflight'))
    await waitFor(() => {
      expect(screen.getByTestId('gi-bench-independence-badge').textContent).toMatch(
        /External independent/i,
      )
    })
    expect(screen.getByTestId('gi-bench-preflight-panel').textContent).toContain(
      'V4 disponibili: 5',
    )
    expect(screen.getByTestId('gi-bench-missing')).toBeTruthy()
  })

  it('full disabilitato prima del pilot completed', () => {
    render(
      <HistoricalRunGoalIntensityBenchmark
        runId={1}
        runStatus="completed"
        seasonLabel="2021/22"
        snapshotsTotal={10}
      />,
    )
    expect(screen.getByTestId('gi-bench-full').hasAttribute('disabled')).toBe(true)
  })

  it('mostra warning overlap', async () => {
    vi.mocked(api.goalIntensityBenchmarkPreflight).mockResolvedValue({
      status: 'preview',
      run: { id: 1, status: 'completed' },
      bundle: {
        id: 9,
        version: 'v',
        status: 'frozen_external_benchmark_candidate',
        is_active: false,
      },
      independence: {
        status: 'partial_development_overlap',
        scientific_label: 'historical_diagnostic_replay',
        overlap_count: 3,
        overlap_pct: 12,
      },
      availability: { blocked: false },
      pilot: { selected: 10 },
      checks: { external_api_calls: 0, base_run_writes: 0, full_scan_required: false },
      pilot_allowed: true,
    })
    render(
      <HistoricalRunGoalIntensityBenchmark runId={1} runStatus="completed" seasonLabel="2021/22" />,
    )
    fireEvent.click(screen.getByTestId('gi-bench-preflight'))
    await waitFor(() => {
      expect(screen.getByTestId('gi-bench-overlap-warning')).toBeTruthy()
    })
  })

  it('avvia pilot con token corretto', async () => {
    vi.mocked(api.startGoalIntensityBenchmarkJob).mockResolvedValue({
      id: 55,
      job_id: 55,
      historical_run_id: 1,
      bundle_id: 9,
      job_version: 'v1',
      mode: 'pilot',
      status: 'queued',
      progress_pct: 0,
      paired_complete: 0,
    })
    render(
      <HistoricalRunGoalIntensityBenchmark runId={1} runStatus="completed" seasonLabel="2021/22" />,
    )
    fireEvent.click(screen.getByTestId('gi-bench-pilot'))
    await waitFor(() => {
      expect(api.startGoalIntensityBenchmarkJob).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          mode: 'pilot',
          confirm: api.GI_HISTORICAL_BENCHMARK_PILOT_CONFIRM,
        }),
      )
    })
  })
})
