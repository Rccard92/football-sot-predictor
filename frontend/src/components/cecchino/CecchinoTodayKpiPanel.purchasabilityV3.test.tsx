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
  rows: [
    {
      market_key: 'AWAY',
      segno: '2',
      label: '2',
      quota_book: 3,
      quota_cecchino: 2.5,
      prob_book: 0.33,
      prob_cecchino: 0.4,
      edge_pct: 20,
      vantaggio_prob: 0.07,
      score_acquisto: 0.4,
      rating: 60,
      status: 'ok',
    },
  ],
}

afterEach(() => {
  cleanup()
})

describe('CecchinoTodayKpiPanel — purchasability V3 decoupled', () => {
  it('non mostra celle V3 Acquistabilità', () => {
    render(<CecchinoTodayKpiPanel panel={panel} todayFixtureId={1} />)
    expect(screen.queryByTestId('purchasability-v3-cell')).toBeNull()
    expect(screen.queryByText('V3 attuale')).toBeNull()
  })
})
