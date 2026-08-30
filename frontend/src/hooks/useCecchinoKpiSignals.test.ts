/** @vitest-environment jsdom */
import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  KpiSignalsBucket,
  KpiSignalsDiagnosticsPayload,
  KpiSignalsSummaryResponse,
} from '../lib/cecchinoKpiSignalsApi'

const getKpiSignalsSummary = vi.fn()
const getKpiSignalsActivations = vi.fn()
const getKpiSignalsDiagnostics = vi.fn()

vi.mock('../lib/cecchinoKpiSignalsApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/cecchinoKpiSignalsApi')>()
  return {
    ...actual,
    getKpiSignalsSummary: (...args: unknown[]) => getKpiSignalsSummary(...args),
    getKpiSignalsActivations: (...args: unknown[]) => getKpiSignalsActivations(...args),
    getKpiSignalsDiagnostics: (...args: unknown[]) => getKpiSignalsDiagnostics(...args),
    backfillKpiSignals: vi.fn(),
    revaluateKpiSignals: vi.fn(),
    buildKpiSignalsExportUrl: vi.fn(() => ''),
  }
})

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

import { useCecchinoKpiSignals } from './useCecchinoKpiSignals'

const emptyBucket = (activations: number): KpiSignalsBucket => ({
  activations,
  settled: 0,
  won: 0,
  lost: 0,
  pending: 0,
  win_rate: null,
  avg_book_odds_all: null,
  avg_book_odds_won: null,
  quota_void: null,
  profit_units: null,
  roi_pct: null,
})

function makeSummary(activations: number): KpiSignalsSummaryResponse {
  return {
    status: 'ok',
    filters: {},
    overall: emptyBucket(activations),
    by_rating_bucket: [],
    by_selection: [],
    heatmap: { rows: [], columns: [], cells: [] },
    top: { best_profit: [], best_roi: [], worst_profit: [] },
  }
}

const diagPayload: KpiSignalsDiagnosticsPayload = {
  today_fixtures_count: 5,
  fixtures_with_kpi_panel: 3,
  kpi_rows_seen: 10,
  kpi_signals_created: 0,
  kpi_rows_below_50: 2,
  kpi_rows_without_book_odds: 0,
}

describe('useCecchinoKpiSignals lazy diagnostics', () => {
  beforeEach(() => {
    getKpiSignalsSummary.mockReset()
    getKpiSignalsActivations.mockReset()
    getKpiSignalsDiagnostics.mockReset()
    getKpiSignalsActivations.mockResolvedValue({ activations: [] })
  })

  afterEach(() => {
    cleanup()
  })

  it('activations > 0: include_diagnostics=false e /diagnostics NON chiamato', async () => {
    getKpiSignalsSummary.mockResolvedValue(makeSummary(100))

    const { result } = renderHook(() => useCecchinoKpiSignals())
    await result.current.loadAll()

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(getKpiSignalsSummary).toHaveBeenCalledTimes(1)
    const filters = getKpiSignalsSummary.mock.calls[0][0] as { include_diagnostics?: boolean }
    expect(filters.include_diagnostics).toBe(false)
    expect(getKpiSignalsDiagnostics).not.toHaveBeenCalled()
    expect(result.current.summary?.overall.activations).toBe(100)
    expect(result.current.summary?.diagnostics).toBeUndefined()
  })

  it('activations === 0: /diagnostics chiamato una sola volta', async () => {
    getKpiSignalsSummary.mockResolvedValue(makeSummary(0))
    getKpiSignalsDiagnostics.mockResolvedValue({
      status: 'ok',
      filters: { date_from: '2026-08-30', date_to: '2026-08-30' },
      diagnostics: diagPayload,
    })

    const { result } = renderHook(() => useCecchinoKpiSignals())
    await result.current.loadAll()

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(getKpiSignalsDiagnostics).toHaveBeenCalledTimes(1)
    expect(result.current.summary?.diagnostics).toEqual(diagPayload)
  })
})
