/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminHttpError } from '../../../lib/api'
import { CecchinoRunV2Section } from './CecchinoRunV2Section'

const apiMock = vi.hoisted(() => ({
  listRunsV2: vi.fn(),
  getRunV2: vi.fn(),
  startRunV2: vi.fn(),
  resumeRunV2: vi.fn(),
  cancelRunV2: vi.fn(),
  downloadRunV2Export: vi.fn(),
  preflightRunV2: vi.fn(),
}))

vi.mock('../../../lib/cecchinoRunV2Api', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/cecchinoRunV2Api')>(
    '../../../lib/cecchinoRunV2Api',
  )
  return { ...actual, ...apiMock }
})

const authMock = vi.hoisted(() => ({
  getAdminSession: vi.fn(),
  adminLogin: vi.fn(),
  adminLogout: vi.fn(),
}))

vi.mock('../../../lib/adminAuthApi', () => authMock)

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
    season_label: '2024/2025',
    max_matches: null,
    requested_at: '2026-09-09T20:00:00Z',
    started_at: '2026-09-09T20:00:00Z',
    completed_at: '2026-09-09T21:00:00Z',
    created_at: '2026-09-09T20:00:00Z',
    updated_at: '2026-09-09T21:00:00Z',
    matches_total: 3800,
    matches_processed: 3800,
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
    module_policy: { season_label: '2024/2025', season_scope: '2024/2025' },
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

async function selectSeasonReady(
  season = '2024/2025',
  options: { expectEnabled?: boolean } = {},
) {
  const expectEnabled = options.expectEnabled !== false
  fireEvent.change(screen.getByTestId('run-v2-season-select'), {
    target: { value: season },
  })
  await waitFor(() => expect(apiMock.preflightRunV2).toHaveBeenCalled())
  await waitFor(() => expect(screen.getByTestId('run-v2-preflight-panel')).toBeTruthy())
  if (expectEnabled) {
    await waitFor(() =>
      expect(screen.getByTestId('run-v2-start-full').hasAttribute('disabled')).toBe(false),
    )
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  apiMock.listRunsV2.mockResolvedValue([makeRun()])
  apiMock.preflightRunV2.mockResolvedValue({
    season_label: '2024/2025',
    status: 'ready',
    matches_total: 3800,
    competitions_count: 5,
    competitions: ['E0', 'I1', 'D1', 'SP1', 'F1'],
    datasets_count: 5,
    date_range: { start: '2024-08-01T00:00:00Z', end: '2025-05-31T00:00:00Z' },
    blocking_anomalies: [],
    warnings: [],
  })
  authMock.getAdminSession.mockResolvedValue({ authenticated: false, expires_in: 0 })
  authMock.adminLogin.mockResolvedValue({ authenticated: true })
  authMock.adminLogout.mockResolvedValue({ authenticated: false })
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

  it('senza stagione i pulsanti Pilot/Full restano disabilitati', async () => {
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())
    expect(screen.getByTestId('run-v2-start-full').hasAttribute('disabled')).toBe(true)
    expect(screen.getByTestId('run-v2-start-pilot').hasAttribute('disabled')).toBe(true)
  })

  it('con stagione ready mostra i dati disponibili e abilita i pulsanti', async () => {
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())
    await selectSeasonReady()
    expect(screen.getByTestId('run-v2-preflight-panel').textContent).toContain('3800')
    expect(screen.getByTestId('run-v2-preflight-panel').textContent).toContain('2024/2025')
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
    await selectSeasonReady()

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
    await selectSeasonReady('2024/2025', { expectEnabled: false })

    expect(screen.getByTestId('run-v2-start-full').hasAttribute('disabled')).toBe(true)
  })

  it("senza sessione admin l'avvio apre il login invece di partire", async () => {
    apiMock.startRunV2.mockRejectedValue(
      new AdminHttpError(401, 'Sessione admin assente o scaduta', null),
    )
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())
    await selectSeasonReady()

    fireEvent.click(screen.getByTestId('run-v2-start-full'))
    fireEvent.click(screen.getByTestId('run-v2-confirm-start'))

    await waitFor(() => expect(screen.getByTestId('run-v2-login-dialog')).toBeTruthy())
    expect(apiMock.startRunV2).toHaveBeenCalledTimes(1)
  })

  it("dopo il login l'avvio viene ripetuto senza rifare il percorso", async () => {
    apiMock.startRunV2
      .mockRejectedValueOnce(new AdminHttpError(401, 'Sessione admin assente o scaduta', null))
      .mockResolvedValueOnce(
        makeRun({ run_id: 21, status: 'pending', effective_status: 'pending' }),
      )
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())
    await selectSeasonReady()

    fireEvent.click(screen.getByTestId('run-v2-start-full'))
    fireEvent.click(screen.getByTestId('run-v2-confirm-start'))
    await waitFor(() => expect(screen.getByTestId('run-v2-login-dialog')).toBeTruthy())

    fireEvent.change(screen.getByTestId('run-v2-login-password'), {
      target: { value: 'password-admin' },
    })
    fireEvent.click(screen.getByTestId('run-v2-login-submit'))

    await waitFor(() => expect(apiMock.startRunV2).toHaveBeenCalledTimes(2))
    expect(authMock.adminLogin).toHaveBeenCalledWith('password-admin')
    await waitFor(() => expect(screen.queryByTestId('run-v2-login-dialog')).toBeNull())
  })

  it('la password admin non finisce mai nel bundle o nelle chiamate RUN V2', async () => {
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())
    await selectSeasonReady()

    fireEvent.click(screen.getByTestId('run-v2-start-full'))
    fireEvent.click(screen.getByTestId('run-v2-confirm-start'))

    await waitFor(() => expect(apiMock.startRunV2).toHaveBeenCalled())
    const args = JSON.stringify(apiMock.startRunV2.mock.calls)
    expect(args.toLowerCase()).not.toContain('password')
    expect(args.toLowerCase()).not.toContain('secret')
    expect(args).toContain('2024/2025')
  })

  it('pilot passa season + maxMatches 50', async () => {
    apiMock.startRunV2.mockResolvedValue(
      makeRun({ run_id: 22, run_scope: 'pilot', max_matches: 50 }),
    )
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())
    await selectSeasonReady()

    fireEvent.click(screen.getByTestId('run-v2-start-pilot'))
    fireEvent.click(screen.getByTestId('run-v2-confirm-start'))

    await waitFor(() => expect(apiMock.startRunV2).toHaveBeenCalled())
    expect(apiMock.startRunV2).toHaveBeenCalledWith({
      season: '2024/2025',
      maxMatches: 50,
    })
  })

  it('pilota maturo passa eligible_per_competition=3', async () => {
    apiMock.startRunV2.mockResolvedValue(
      makeRun({
        run_id: 23,
        run_scope: 'balanced_pilot',
        max_matches: null,
        module_policy: {
          pilot_strategy: 'eligible_per_competition',
          eligible_per_competition: 3,
        },
      }),
    )
    renderSection()
    await waitFor(() => expect(screen.getByTestId('run-v2-row-5')).toBeTruthy())
    await selectSeasonReady()

    fireEvent.click(screen.getByTestId('run-v2-start-balanced-pilot'))
    fireEvent.click(screen.getByTestId('run-v2-confirm-start'))

    await waitFor(() => expect(apiMock.startRunV2).toHaveBeenCalled())
    expect(apiMock.startRunV2).toHaveBeenCalledWith({
      season: '2024/2025',
      pilotStrategy: 'eligible_per_competition',
      eligiblePerCompetition: 3,
    })
  })
})
