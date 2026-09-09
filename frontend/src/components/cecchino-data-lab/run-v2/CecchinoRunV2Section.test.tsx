/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CecchinoRunV2Section } from './CecchinoRunV2Section'

const apiMock = vi.hoisted(() => ({
  listRunsV2: vi.fn(),
  getRunV2: vi.fn(),
  startRunV2: vi.fn(),
  resumeRunV2: vi.fn(),
  cancelRunV2: vi.fn(),
  downloadRunV2Export: vi.fn(),
}))

vi.mock('../../../lib/cecchinoRunV2Api', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/cecchinoRunV2Api')>(
    '../../../lib/cecchinoRunV2Api',
  )
  return { ...actual, ...apiMock }
})

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), message: vi.fn() },
}))

function makeRun(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 5,
    run_version: 'cecchino_run_v2',
    status: 'completed',
    effective_status: 'completed',
    is_stale: false,
    worker_alive: false,
    can_resume: false,
    can_cancel: false,
    heartbeat_at: null,
    heartbeat_age_seconds: 2,
    stale_heartbeat_seconds: 900,
    run_scope: 'full',
    max_matches: null,
    requested_at: '2026-09-09T20:00:00Z',
    started_at: '2026-09-09T20:00:00Z',
    completed_at: '2026-09-09T21:00:00Z',
    created_at: '2026-09-09T20:00:00Z',
    updated_at: '2026-09-09T21:00:00Z',
    matches_total: 31000,
    matches_processed: 31000,
    matches_error: 0,
    market_rows_written: 527000,
    leakage_violations: 0,
    progress_pct: 100,
    min_kickoff_at: null,
    max_kickoff_at: null,
    current_competition: null,
    last_processed_kickoff_at: null,
    cancel_requested: false,
    quote_policy: null,
    module_policy: null,
    coverage: null,
    summary: null,
    leakage_audit: null,
    warnings: null,
    error: null,
    source_git_commit: null,
    source_git_commit_source: null,
    source_revision_status: null,
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  apiMock.listRunsV2.mockResolvedValue([makeRun()])
})

function renderSection() {
  return render(
    <MemoryRouter>
      <CecchinoRunV2Section refreshKey={0} />
    </MemoryRouter>,
  )
}

describe('CecchinoRunV2Section', () => {
  it('mostra Apri, Analizza ed Esporta FULL per una RUN completata', async () => {
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())

    expect(screen.getByTestId('run-v2-open-5')).toBeTruthy()
    expect(screen.getByTestId('run-v2-export-full-5')).toBeTruthy()

    const analyze = screen.getByTestId('run-v2-analyze-5')
    expect(analyze.getAttribute('href')).toBe('/cecchino-lab?tab=run_v2&run_v2_id=5')
  })

  it('non collega mai la V2 al Pattern Lab V1', async () => {
    const { container } = renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())

    const hrefs = Array.from(container.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs.some((h) => h?.includes('pattern_lab'))).toBe(false)
    expect(hrefs.some((h) => h?.includes('run_ids'))).toBe(false)
  })

  it('Apri mostra il pannello di dettaglio con coverage ed export', async () => {
    apiMock.listRunsV2.mockResolvedValue([
      makeRun({
        summary: {
          competitions: [
            { competition: 'E0', season_label: '2021/2022', matches: 380, first_kickoff: null, last_kickoff: null },
          ],
          market_coverage: [
            {
              market_key: 'HOME',
              export_key: 'HOME',
              observation_layer: 'core_strict',
              rows: 31000,
              rows_with_quote: 30500,
              rows_with_prediction: 31000,
              quote_coverage_pct: 98.39,
              used_for_prediction: true,
              pre_match_input_safe: true,
            },
          ],
          extra_stats_coverage: { snapshots: 31000, with_referee: 28000 },
        },
      }),
    ])
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())

    fireEvent.click(screen.getByTestId('run-v2-open-5'))

    expect(screen.getByTestId('run-v2-detail-5')).toBeTruthy()
    expect(screen.getByText('Competizioni e stagioni')).toBeTruthy()
    expect(screen.getByText('Copertura quote')).toBeTruthy()
    expect(screen.getByText('Audit anti-leakage')).toBeTruthy()
    expect(screen.getByTestId('run-v2-export-5-FULL.csv')).toBeTruthy()
    expect(screen.getByTestId('run-v2-export-5-run_summary.json')).toBeTruthy()
  })

  it('Esporta FULL scarica FULL.csv', async () => {
    apiMock.downloadRunV2Export.mockResolvedValue(undefined)
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())

    fireEvent.click(screen.getByTestId('run-v2-export-full-5'))

    await waitFor(() =>
      expect(apiMock.downloadRunV2Export).toHaveBeenCalledWith(5, 'FULL.csv'),
    )
  })

  it('una RUN rimasta senza worker appare interrotta e riprendibile', async () => {
    apiMock.listRunsV2.mockResolvedValue([
      makeRun({
        run_id: 9,
        status: 'running',
        effective_status: 'interrupted',
        is_stale: true,
        can_resume: true,
        can_cancel: true,
        matches_processed: 12000,
        progress_pct: 38.7,
      }),
    ])
    apiMock.resumeRunV2.mockResolvedValue(makeRun({ run_id: 9, status: 'pending' }))
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-9')).toBeTruthy())

    expect(screen.getByText(/Interrotta/)).toBeTruthy()
    expect(screen.getByTestId('run-v2-stale-badge-9')).toBeTruthy()

    fireEvent.click(screen.getByTestId('run-v2-resume-9'))
    await waitFor(() => expect(apiMock.resumeRunV2).toHaveBeenCalledWith(9))
  })

  it('lo stato interrotto non viene trattato come run attiva: si puo ancora avviare', async () => {
    apiMock.listRunsV2.mockResolvedValue([
      makeRun({ run_id: 9, status: 'running', effective_status: 'interrupted', is_stale: true }),
    ])
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-9')).toBeTruthy())

    expect(screen.getByTestId('run-v2-start-full').hasAttribute('disabled')).toBe(false)
    expect(screen.queryByTestId('run-v2-active-panel')).toBeNull()
  })

  it('stale_active_run mostra il banner con Riprendi e Annulla invece di un errore secco', async () => {
    const { RunV2ApiError } = await vi.importActual<
      typeof import('../../../lib/cecchinoRunV2Api')
    >('../../../lib/cecchinoRunV2Api')
    apiMock.startRunV2.mockRejectedValue(
      new RunV2ApiError(409, 'RUN interrotta', 'stale_active_run', {
        run_id: 9,
        resumable: true,
      }),
    )
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())

    fireEvent.click(screen.getByTestId('run-v2-start-full'))
    fireEvent.click(screen.getByTestId('run-v2-confirm-start'))

    await waitFor(() => expect(screen.getByTestId('run-v2-blocked-banner')).toBeTruthy())
    expect(screen.getByTestId('run-v2-blocked-resume')).toBeTruthy()
    expect(screen.getByTestId('run-v2-blocked-cancel')).toBeTruthy()
  })

  it('una RUN in corso blocca un secondo avvio', async () => {
    apiMock.listRunsV2.mockResolvedValue([
      makeRun({
        run_id: 11,
        status: 'running',
        effective_status: 'running',
        can_cancel: true,
        matches_processed: 500,
        progress_pct: 1.6,
      }),
    ])
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-active-panel')).toBeTruthy())

    expect(screen.getByTestId('run-v2-start-full').hasAttribute('disabled')).toBe(true)
  })
})
