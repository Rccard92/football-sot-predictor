/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ObservationDashboard, ObservationModelOverview, ObservationTally } from '../lib/cecchinoLiveApi'

function tally(closed: number, won: number, roi: number | null, profit = 0): ObservationTally {
  return { plays: closed, closed, pending: 0, won, lost: closed - won, won_pct: closed ? (100 * won) / closed : null, roi_pct: roi, profit, avg_quota: 1.9, sample: 'presto per dirlo' }
}

function model(indexAvailable: boolean, indexRoi: number | null, patternRoi: number | null): ObservationModelOverview {
  const t = tally(10, 6, indexRoi, 1)
  return {
    index: {
      available: indexAvailable,
      plays: t,
      all_predictions: t,
      last7: t,
      top: { '90-100': t, '70-90': t },
      by_pattern: { confermate: t, in_contrasto: t, altri_pattern: t, senza_pattern: t },
      bands: [{ key: '90-100', ...t }],
      by_market: [{ key: 'HOME', ...t }],
      by_family: [{ key: 'esito', label: 'Esito finale', ...t }],
      by_league: [{ key: 'Brasile · Serie B', ...t }],
    },
    patterns: {
      plays: tally(8, 4, patternRoi, -1),
      last7: tally(8, 4, patternRoi, -1),
      with_book_conditions: tally(2, 1, 5),
      by_market: [{ key: 'OVER_2_5', ...tally(8, 4, patternRoi), hist_win_pct: 55, hist_roi_pct: 6 }],
      by_family: [],
      by_league: [],
      concordance: [],
    },
    daily: [
      { scan_date: '2026-09-16', index: t, pattern: tally(8, 4, patternRoi), cumulative_index_profit: 1, cumulative_pattern_profit: -1, fixtures: [] },
    ],
  }
}

const dashboard = {
  models: ['V2', 'V2.5', 'V3'],
  book_reference: 'Bet365',
  totals: { fixtures: 3, fixtures_settled: 3, common_fixtures: 0 },
  engines: {},
  models_overview: {
    thresholds: { index_min_score: 70, playable_min_quota: 1.5, sample_early: 100, sample_reliable: 300 },
    models: { V2: model(false, null, -3), 'V2.5': model(true, -2, 4), V3: model(true, 5, -6) },
    agreement: { 'entrambi_90+': tally(3, 2, 10) },
  },
} as unknown as ObservationDashboard

vi.mock('../lib/cecchinoLiveApi', async () => {
  const actual = await vi.importActual('../lib/cecchinoLiveApi')
  return { ...actual, getObservationDashboard: vi.fn(async () => dashboard) }
})

describe('LiveObservationPage', () => {
  afterEach(() => cleanup())

  it('in cima dice quale modello rende di più per indice e per pattern', async () => {
    const { LiveObservationPage } = await import('./LiveObservationPage')
    render(<LiveObservationPage />)
    await waitFor(() => expect(screen.getByText(/Indice di acquistabilità: va meglio la V3/)).toBeTruthy())
    expect(screen.getByText(/Pattern con quota: va meglio la V2.5/)).toBeTruthy()
    expect(screen.getByText(/Indice orchestratore non previsto per la V2/)).toBeTruthy()
    // nessun bookmaker come riferimento nella pagina
    expect(screen.queryByText(/riferimento/)).toBeNull()
  })

  it('il dettaglio cambia modello con le schede', async () => {
    const { LiveObservationPage } = await import('./LiveObservationPage')
    render(<LiveObservationPage />)
    await waitFor(() => screen.getAllByRole('tab'))
    fireEvent.click(screen.getByRole('tab', { name: /V2\.5/ }))
    expect(screen.getByText('Giornata per giornata · V2.5')).toBeTruthy()
  })
})
