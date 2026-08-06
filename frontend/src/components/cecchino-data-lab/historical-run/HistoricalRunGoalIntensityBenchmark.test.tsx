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

const allowedPreflight = {
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
    v4_persisted_available: 2,
    v4_reconstructed_available: 3,
    v4_total_available: 5,
    v4_reconstruction_input_mismatch: 0,
    v4_reconstruction_kpi_mismatch: 0,
    v4_missing_context_data: 0,
    v5_features_rebuildable: 8,
    v5_rebuildable: 8,
    paired_complete_estimate: 5,
    paired_coverage_pct: 50,
    five_models_probe_n: 5,
    five_models_probe_ok: 5,
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
  v4_persisted_available: 2,
  v4_reconstructed_available: 3,
  v4_total_available: 5,
  v5_rebuildable: 8,
  paired_complete_estimate: 5,
  paired_coverage_pct: 50,
  pilot_paired_estimate: 4,
  five_models_probe_n: 5,
  five_models_probe_ok: 5,
  pilot_data_gate_status: 'ok',
  pilot_allowed: true,
  blocking_reasons: [],
  warnings: [],
}

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
    vi.mocked(api.goalIntensityBenchmarkPreflight).mockResolvedValue(allowedPreflight as never)

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
    expect(screen.getByTestId('gi-bench-v4-persisted').textContent).toContain('2')
    expect(screen.getByTestId('gi-bench-v4-reconstructed').textContent).toContain('3')
    expect(screen.getByTestId('gi-bench-v4-total').textContent).toContain('5')
    expect(screen.getByTestId('gi-bench-v5-rebuildable').textContent).toContain('8')
    expect(screen.getByTestId('gi-bench-paired-estimate').textContent).toContain('5')
    expect(screen.getByTestId('gi-bench-five-models-probe').textContent).toContain('5/5')
    expect(screen.getByTestId('gi-bench-v4-reconstruction-note').textContent).toMatch(
      /formula V4 frozen/i,
    )
    expect(screen.getByTestId('gi-bench-missing')).toBeTruthy()
  })

  it('disabilita pilot senza preflight e con pilot_allowed=false', async () => {
    render(
      <HistoricalRunGoalIntensityBenchmark runId={1} runStatus="completed" seasonLabel="2021/22" />,
    )
    expect(screen.getByTestId('gi-bench-pilot').hasAttribute('disabled')).toBe(true)

    vi.mocked(api.goalIntensityBenchmarkPreflight).mockResolvedValue({
      ...allowedPreflight,
      pilot_allowed: false,
      pilot_data_gate_status: 'blocked',
      blocking_reasons: ['paired_complete_estimate_zero'],
      paired_complete_estimate: 0,
      availability: {
        ...allowedPreflight.availability,
        paired_complete_estimate: 0,
        blocked: true,
      },
    } as never)

    fireEvent.click(screen.getByTestId('gi-bench-preflight'))
    await waitFor(() => {
      expect(screen.getByTestId('gi-bench-blocking-reasons').textContent).toContain(
        'paired_complete_estimate_zero',
      )
    })
    expect(screen.getByTestId('gi-bench-pilot').hasAttribute('disabled')).toBe(true)
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

  it('full disabilitato se pilot_gate backend non ok', async () => {
    vi.mocked(api.listGoalIntensityBenchmarkJobs).mockResolvedValue({
      jobs: [
        {
          id: 10,
          job_id: 10,
          historical_run_id: 1,
          bundle_id: 9,
          job_version: 'v1',
          mode: 'pilot',
          status: 'completed',
          progress_pct: 100,
          paired_complete: 0,
          pilot_gate: { ok: false, reasons: ['pilot_zero_paired_complete'] },
        },
      ],
    })
    render(
      <HistoricalRunGoalIntensityBenchmark runId={1} runStatus="completed" seasonLabel="2021/22" />,
    )
    await waitFor(() => {
      expect(screen.getByTestId('gi-bench-pilot-gate-reasons').textContent).toContain(
        'pilot_zero_paired_complete',
      )
    })
    expect(screen.getByTestId('gi-bench-full').hasAttribute('disabled')).toBe(true)
  })

  it('full abilitato solo con pilot_gate.ok dal backend', async () => {
    vi.mocked(api.listGoalIntensityBenchmarkJobs).mockResolvedValue({
      jobs: [
        {
          id: 11,
          job_id: 11,
          historical_run_id: 1,
          bundle_id: 9,
          job_version: 'v1',
          mode: 'pilot',
          status: 'completed',
          progress_pct: 100,
          paired_complete: 3,
          pilot_gate: { ok: true, reasons: [] },
        },
      ],
    })
    render(
      <HistoricalRunGoalIntensityBenchmark runId={1} runStatus="completed" seasonLabel="2021/22" />,
    )
    await waitFor(() => {
      expect(screen.getByTestId('gi-bench-full').hasAttribute('disabled')).toBe(false)
    })
  })

  it('mostra warning stale e resume quando can_resume', async () => {
    vi.mocked(api.listGoalIntensityBenchmarkJobs).mockResolvedValue({
      jobs: [
        {
          id: 12,
          job_id: 12,
          historical_run_id: 1,
          bundle_id: 9,
          job_version: 'v1',
          mode: 'pilot',
          status: 'running',
          effective_status: 'interrupted',
          is_stale: true,
          can_resume: true,
          progress_pct: 40,
          paired_complete: 2,
        },
      ],
    })
    render(
      <HistoricalRunGoalIntensityBenchmark runId={1} runStatus="completed" seasonLabel="2021/22" />,
    )
    await waitFor(() => {
      expect(screen.getByTestId('gi-bench-stale-warning')).toBeTruthy()
      expect(screen.getByTestId('gi-bench-resume')).toBeTruthy()
    })
  })

  it('mostra warning overlap', async () => {
    vi.mocked(api.goalIntensityBenchmarkPreflight).mockResolvedValue({
      ...allowedPreflight,
      independence: {
        status: 'partial_development_overlap',
        scientific_label: 'historical_diagnostic_replay',
        overlap_count: 3,
        overlap_pct: 12,
      },
    } as never)
    render(
      <HistoricalRunGoalIntensityBenchmark runId={1} runStatus="completed" seasonLabel="2021/22" />,
    )
    fireEvent.click(screen.getByTestId('gi-bench-preflight'))
    await waitFor(() => {
      expect(screen.getByTestId('gi-bench-overlap-warning')).toBeTruthy()
    })
  })

  it('avvia pilot con token corretto dopo preflight allowed', async () => {
    vi.mocked(api.goalIntensityBenchmarkPreflight).mockResolvedValue(allowedPreflight as never)
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
    fireEvent.click(screen.getByTestId('gi-bench-preflight'))
    await waitFor(() => {
      expect(screen.getByTestId('gi-bench-pilot').hasAttribute('disabled')).toBe(false)
    })
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
