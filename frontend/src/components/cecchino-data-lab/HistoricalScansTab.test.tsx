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

describe('HistoricalScansTab Pattern Lab navigation', () => {
  it('mostra solo Analizza verso Pattern Lab; nasconde i vecchi 5 pulsanti', async () => {
    render(
      <MemoryRouter>
        <HistoricalScansTab refreshKey={0} />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('historical-analyze-link-3')).toBeTruthy())
    const analyze = screen.getByTestId('historical-analyze-link-3')
    expect(analyze.getAttribute('href')).toBe('/cecchino-lab/pattern-lab?run_ids=3')
    expect(screen.queryByTestId('historical-dashboard-link-3')).toBeNull()
    expect(screen.queryByTestId('historical-gi-benchmark-link-3')).toBeNull()
    expect(screen.queryByTestId('historical-kpi-link-3')).toBeNull()
    expect(screen.queryByTestId('historical-signals-af-link-3')).toBeNull()
    expect(screen.queryByTestId('historical-report-link-3')).toBeNull()
  })
})
