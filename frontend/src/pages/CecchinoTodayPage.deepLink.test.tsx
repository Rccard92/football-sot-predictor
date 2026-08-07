/** @vitest-environment jsdom */
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CecchinoTodayPage } from './CecchinoTodayPage'

const apiMock = vi.hoisted(() => ({
  getCecchinoTodayDays: vi.fn(),
  getCecchinoTodayList: vi.fn(),
  getCecchinoTodayDetail: vi.fn(),
  getCecchinoTodayLatestScanJob: vi.fn(),
  getCecchinoTodayScanJob: vi.fn(),
  todayIsoRome: vi.fn(() => '2026-08-08'),
  logCecchinoTodayDebug: vi.fn(),
  SCAN_JOB_POLL_MS: 2500,
}))

vi.mock('../lib/cecchinoTodayApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/cecchinoTodayApi')>(
    '../lib/cecchinoTodayApi',
  )
  return {
    ...actual,
    getCecchinoTodayDays: apiMock.getCecchinoTodayDays,
    getCecchinoTodayList: apiMock.getCecchinoTodayList,
    getCecchinoTodayDetail: apiMock.getCecchinoTodayDetail,
    getCecchinoTodayLatestScanJob: apiMock.getCecchinoTodayLatestScanJob,
    getCecchinoTodayScanJob: apiMock.getCecchinoTodayScanJob,
    todayIsoRome: apiMock.todayIsoRome,
    logCecchinoTodayDebug: apiMock.logCecchinoTodayDebug,
    SCAN_JOB_POLL_MS: apiMock.SCAN_JOB_POLL_MS,
  }
})

function listResponse(date: string, fixtureIds: number[]) {
  return {
    status: 'ok',
    version: 'v1',
    date,
    scan_date: date,
    is_scanned: true,
    total: fixtureIds.length,
    summary: {
      eligible_count: fixtureIds.length,
      upcoming_count: fixtureIds.length,
      live_count: 0,
      finished_count: 0,
      excluded_count: 0,
      last_scan_at: `${date}T10:00:00Z`,
    },
    filters: {
      countries: ['Sweden'],
      leagues: ['Division 2'],
      statuses: ['upcoming'],
    },
    countries: [
      {
        country_name: 'Sweden',
        country_flag_url: null,
        leagues: [
          {
            league_name: 'Division 2',
            league_logo_url: null,
            fixtures: fixtureIds.map((id) => ({
              today_fixture_id: id,
              id,
              provider_fixture_id: id,
              local_fixture_id: null,
              competition_id: null,
              home_team_name: `Home ${id}`,
              away_team_name: `Away ${id}`,
              home_team_logo_url: null,
              away_team_logo_url: null,
              kickoff: `${date}T13:00:00Z`,
              status: 'upcoming' as const,
              status_label: 'Upcoming',
              score: { home: null, away: null },
              cecchino_recommended_prediction: {
                label: null,
                market: null,
                confidence: null,
              },
              kpi_status: 'ok',
              signals_status: 'ok',
            })),
          },
        ],
      },
    ],
  }
}

function renderToday(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/cecchino-today" element={<CecchinoTodayPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CecchinoTodayPage deep-link', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })

    apiMock.getCecchinoTodayDays.mockReset()
    apiMock.getCecchinoTodayList.mockReset()
    apiMock.getCecchinoTodayDetail.mockReset()
    apiMock.getCecchinoTodayLatestScanJob.mockReset()
    apiMock.getCecchinoTodayScanJob.mockReset()
    apiMock.todayIsoRome.mockReturnValue('2026-08-08')

    apiMock.getCecchinoTodayDays.mockResolvedValue({
      status: 'ok',
      version: 'v1',
      timezone: 'Europe/Rome',
      today: '2026-08-08',
      tomorrow: '2026-08-09',
      selected_default: '2026-08-08',
      days: [
        {
          date: '2026-08-07',
          label: 'Ieri',
          is_today: false,
          is_future: false,
          is_scanned: true,
          eligible_count: 2,
          excluded_count: 0,
          upcoming_count: 2,
          live_count: 0,
          finished_count: 0,
          last_scan_at: '2026-08-07T10:00:00Z',
          scan_state: 'scanned',
          status: 'available',
        },
        {
          date: '2026-08-08',
          label: 'Oggi',
          is_today: true,
          is_future: false,
          is_scanned: true,
          eligible_count: 2,
          excluded_count: 0,
          upcoming_count: 2,
          live_count: 0,
          finished_count: 0,
          last_scan_at: '2026-08-08T10:00:00Z',
          scan_state: 'scanned',
          status: 'available',
        },
      ],
    })
    apiMock.getCecchinoTodayLatestScanJob.mockResolvedValue(null)
    apiMock.getCecchinoTodayDetail.mockResolvedValue({
      status: 'ok',
      today_fixture_id: 16511,
      kpi_panel_v2: null,
      kpi_panel: null,
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('seleziona fixture da query param dopo caricamento lista', async () => {
    apiMock.getCecchinoTodayList.mockResolvedValue(listResponse('2026-08-07', [16511, 99]))
    renderToday('/cecchino-today?date=2026-08-07&fixture=16511')

    await waitFor(() =>
      expect(apiMock.getCecchinoTodayList).toHaveBeenCalledWith(
        expect.objectContaining({ date: '2026-08-07' }),
      ),
    )
    await waitFor(() =>
      expect(apiMock.getCecchinoTodayDetail).toHaveBeenCalledWith(16511),
    )
  })

  it('fixture assente non crasha e non forza selezione', async () => {
    apiMock.getCecchinoTodayList.mockResolvedValue(listResponse('2026-08-08', [10, 20]))
    renderToday('/cecchino-today?date=2026-08-08&fixture=99999')

    await waitFor(() => expect(apiMock.getCecchinoTodayList).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/Home 10/i)).toBeTruthy())
    expect(apiMock.getCecchinoTodayDetail).not.toHaveBeenCalled()
  })

  it('senza query params mantiene comportamento standard', async () => {
    apiMock.getCecchinoTodayList.mockResolvedValue(listResponse('2026-08-08', [42]))
    renderToday('/cecchino-today')

    await waitFor(() =>
      expect(apiMock.getCecchinoTodayList).toHaveBeenCalledWith(
        expect.objectContaining({ date: '2026-08-08' }),
      ),
    )
    expect(apiMock.getCecchinoTodayDetail).not.toHaveBeenCalled()
  })
})
