/** @vitest-environment jsdom */
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HistoricalScansTab } from './HistoricalScansTab'

const apiMock = vi.hoisted(() => ({
  listHistoricalScans: vi.fn(),
  getHistoricalScan: vi.fn(),
}))

vi.mock('../../lib/cecchinoLabApi', async () => {
  const actual = await vi.importActual<typeof import('../../lib/cecchinoLabApi')>(
    '../../lib/cecchinoLabApi',
  )
  return { ...actual, ...apiMock }
})

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  apiMock.listHistoricalScans.mockResolvedValue([
    {
      id: 3,
      season_label: '2021/2022',
      status: 'completed',
      matches_processed: 100,
      matches_total: 100,
      progress_pct: 100,
      matches_eligible_core: 80,
      matches_excluded: 20,
      matches_error: 0,
      run_scope: 'full',
      is_partial_run: false,
      module_policy_json: { run_scope: 'full' },
    },
  ])
})

describe('HistoricalScansTab STEP 4B navigation', () => {
  it('mostra Analisi KPI, Segnali A–F, Report; nasconde Apri analisi e Verifica replay', async () => {
    render(
      <MemoryRouter>
        <HistoricalScansTab refreshKey={0} />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('historical-kpi-link-3')).toBeTruthy())
    expect(screen.getByTestId('historical-signals-af-link-3')).toBeTruthy()
    expect(screen.getByTestId('historical-report-link-3')).toBeTruthy()
    expect(screen.queryByText('Apri analisi')).toBeNull()
    expect(screen.queryByText(/Verifica replay Acquistabilità/i)).toBeNull()
    expect(screen.queryByText('Dettaglio')).toBeNull()
  })
})
