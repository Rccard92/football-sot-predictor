/** @vitest-environment jsdom */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { CecchinoTodayKpiPanel } from './CecchinoTodayKpiPanel'
import type { CecchinoKpiV2Panel } from '../../lib/cecchinoTodayApi'

vi.mock('../../lib/cecchinoTodayApi', async () => {
  const actual = await vi.importActual<typeof import('../../lib/cecchinoTodayApi')>(
    '../../lib/cecchinoTodayApi',
  )
  return { ...actual, getKpiExplanations: vi.fn() }
})

const panel: CecchinoKpiV2Panel = {
  version: 'kpi_v2',
  bookmaker: { name: 'Betfair', provider_bookmaker_id: 3, provider_source: 'betfair' },
  rows: [
    {
      market_key: 'HOME',
      segno: '1',
      label: '1',
      quota_book: 2.1,
      quota_cecchino: 1.9,
      prob_book: 0.48,
      prob_cecchino: 0.52,
      edge_pct: 10,
      vantaggio_prob: 0.04,
      score_acquisto: 0.5,
      rating: 70,
      rating_label: 'Buona',
      status: 'ok',
    },
  ],
}

afterEach(() => {
  cleanup()
})

describe('CecchinoTodayKpiPanel — no Acquistabilità column', () => {
  it('non mostra colonna Acquistabilità', () => {
    render(<CecchinoTodayKpiPanel panel={panel} todayFixtureId={1} />)
    expect(screen.queryByText('Acquistabilità')).toBeNull()
    expect(screen.queryByTestId('purchasability-version-selector')).toBeNull()
  })
})
