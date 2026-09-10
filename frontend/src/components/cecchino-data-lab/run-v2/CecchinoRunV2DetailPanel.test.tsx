/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import type { CecchinoRunV2, CecchinoRunV2AiBundleJob } from '../../../lib/cecchinoRunV2Api'
import { CecchinoRunV2DetailPanel } from './CecchinoRunV2DetailPanel'

const apiMock = vi.hoisted(() => ({
  createRunV2AiBundleJob: vi.fn(),
  getRunV2AiBundleJob: vi.fn(),
  downloadRunV2AiBundleReady: vi.fn(),
  downloadRunV2Export: vi.fn(),
  getRunV2ExportManifest: vi.fn(),
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

function makeRun(overrides: Partial<CecchinoRunV2> = {}): CecchinoRunV2 {
  return {
    run_id: 21,
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
    season_label: '2024/2025',
    max_matches: null,
    requested_at: '2026-09-09T20:00:00Z',
    started_at: '2026-09-09T20:00:00Z',
    completed_at: '2026-09-09T21:00:00Z',
    created_at: '2026-09-09T20:00:00Z',
    updated_at: '2026-09-09T21:00:00Z',
    matches_total: 100,
    matches_processed: 100,
    matches_error: 0,
    market_rows_written: 1000,
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

function makeJob(overrides: Partial<CecchinoRunV2AiBundleJob> = {}): CecchinoRunV2AiBundleJob {
  return {
    job_id: 'job-1',
    run_id: 21,
    export_schema_version: 'v1',
    status: 'pending',
    phase: 'queued',
    progress_pct: 0,
    progress_message: null,
    retryable: false,
    error_code: null,
    error_message: null,
    filename: null,
    zip_bytes: null,
    poll_after_ms: 10,
    download_ready: false,
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

beforeEach(() => {
  apiMock.createRunV2AiBundleJob.mockReset()
  apiMock.getRunV2AiBundleJob.mockReset()
  apiMock.downloadRunV2AiBundleReady.mockReset()
  apiMock.downloadRunV2Export.mockReset()
  apiMock.getRunV2ExportManifest.mockReset()
})

describe('CecchinoRunV2DetailPanel AI bundle async', () => {
  it('al Prepara chiama solo createRunV2AiBundleJob e non sync GET', async () => {
    apiMock.createRunV2AiBundleJob.mockResolvedValue(
      makeJob({ status: 'building', phase: 'metadata', progress_pct: 75 }),
    )
    apiMock.getRunV2AiBundleJob.mockResolvedValue(
      makeJob({
        status: 'ready',
        phase: 'ready',
        progress_pct: 100,
        download_ready: true,
        filename: 'bundle.zip',
      }),
    )

    render(<CecchinoRunV2DetailPanel run={makeRun()} onClose={() => undefined} />)
    fireEvent.click(screen.getByTestId('run-v2-prepare-ai-bundle-21'))

    await waitFor(() => expect(apiMock.createRunV2AiBundleJob).toHaveBeenCalledWith(21))
    expect(apiMock.downloadRunV2AiBundleReady).not.toHaveBeenCalled()
    expect(apiMock.downloadRunV2Export).not.toHaveBeenCalled()
  })

  it('dopo poll ready mostra Scarica e scarica solo via download ready', async () => {
    apiMock.createRunV2AiBundleJob.mockResolvedValue(
      makeJob({ status: 'building', phase: 'zip', progress_pct: 90, poll_after_ms: 5 }),
    )
    apiMock.getRunV2AiBundleJob
      .mockResolvedValueOnce(
        makeJob({
          status: 'building',
          phase: 'zip',
          progress_pct: 90,
          progress_message: 'Creazione ZIP',
          poll_after_ms: 5,
        }),
      )
      .mockResolvedValueOnce(
        makeJob({
          status: 'ready',
          phase: 'ready',
          progress_pct: 100,
          download_ready: true,
          filename: 'bundle.zip',
        }),
      )
    apiMock.downloadRunV2AiBundleReady.mockResolvedValue(undefined)

    render(<CecchinoRunV2DetailPanel run={makeRun()} onClose={() => undefined} />)
    fireEvent.click(screen.getByTestId('run-v2-prepare-ai-bundle-21'))

    await waitFor(() =>
      expect(screen.getByTestId('run-v2-ai-bundle-status-21').textContent).toContain(
        'Preparazione',
      ),
    )
    await waitFor(() => expect(screen.getByTestId('run-v2-export-ai-bundle-21')).toBeTruthy())
    expect(screen.getByTestId('run-v2-ai-bundle-status-21').textContent).toContain(
      'Pacchetto pronto',
    )

    fireEvent.click(screen.getByTestId('run-v2-export-ai-bundle-21'))
    await waitFor(() => expect(apiMock.downloadRunV2AiBundleReady).toHaveBeenCalledWith(21))
    expect(apiMock.createRunV2AiBundleJob).toHaveBeenCalledTimes(1)
  })

  it('su failed retryable mostra errore e lascia ripremere Prepara', async () => {
    apiMock.createRunV2AiBundleJob.mockResolvedValue(
      makeJob({ status: 'building', phase: 'export_bundle', progress_pct: 10, poll_after_ms: 5 }),
    )
    apiMock.getRunV2AiBundleJob.mockResolvedValue(
      makeJob({
        status: 'failed',
        phase: 'failed',
        progress_pct: 10,
        retryable: true,
        error_message: 'export_failed',
      }),
    )

    render(<CecchinoRunV2DetailPanel run={makeRun()} onClose={() => undefined} />)
    fireEvent.click(screen.getByTestId('run-v2-prepare-ai-bundle-21'))

    await waitFor(() =>
      expect(screen.getByTestId('run-v2-ai-bundle-status-21').textContent).toContain(
        'Preparazione fallita',
      ),
    )
    expect(screen.getByTestId('run-v2-ai-bundle-status-21').textContent).toContain(
      'ripremi Prepara',
    )
    expect(screen.queryByTestId('run-v2-export-ai-bundle-21')).toBeNull()
    expect(toast.error).toHaveBeenCalled()
    expect(screen.getByTestId('run-v2-prepare-ai-bundle-21').hasAttribute('disabled')).toBe(
      false,
    )
  })

  it('su interrupted retryable consente un nuovo Prepara', async () => {
    apiMock.createRunV2AiBundleJob
      .mockResolvedValueOnce(
        makeJob({ status: 'building', phase: 'metadata', progress_pct: 75, poll_after_ms: 5 }),
      )
      .mockResolvedValueOnce(
        makeJob({
          status: 'ready',
          phase: 'ready',
          progress_pct: 100,
          download_ready: true,
        }),
      )
    apiMock.getRunV2AiBundleJob.mockResolvedValue(
      makeJob({
        status: 'interrupted',
        phase: 'failed',
        retryable: true,
        error_message: 'worker_restart',
      }),
    )

    render(<CecchinoRunV2DetailPanel run={makeRun()} onClose={() => undefined} />)
    fireEvent.click(screen.getByTestId('run-v2-prepare-ai-bundle-21'))

    await waitFor(() =>
      expect(screen.getByTestId('run-v2-ai-bundle-status-21').textContent).toContain(
        'Preparazione interrotta',
      ),
    )
    expect(screen.queryByTestId('run-v2-export-ai-bundle-21')).toBeNull()

    fireEvent.click(screen.getByTestId('run-v2-prepare-ai-bundle-21'))
    await waitFor(() => expect(apiMock.createRunV2AiBundleJob).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.getByTestId('run-v2-export-ai-bundle-21')).toBeTruthy())
  })
})
