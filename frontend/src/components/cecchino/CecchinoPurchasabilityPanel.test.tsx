/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CecchinoPurchasabilityPanel } from './CecchinoPurchasabilityPanel'
import type { CecchinoPurchasabilityV31Item } from '../../lib/cecchinoTodayApi'
import {
  AWAY_V31_ITEM,
  GATE_FAILED_RATING_V31_ITEM,
  NON_CALCULABLE_MISSING_QUOTE_V31_ITEM,
} from './fixtures/purchasabilityV31Fixtures'

vi.mock('../../lib/cecchinoTodayApi', async () => {
  const actual = await vi.importActual<typeof import('../../lib/cecchinoTodayApi')>(
    '../../lib/cecchinoTodayApi',
  )
  return {
    ...actual,
    getPurchasabilityAuditExport: vi.fn(),
  }
})

import { getPurchasabilityAuditExport } from '../../lib/cecchinoTodayApi'

const DRAW_ITEM: CecchinoPurchasabilityV31Item = {
  market_key: 'DRAW',
  market_label: 'X',
  status: 'score',
  score: 42,
  score_v31: 42,
  class: 'Media',
  reading_short: 'Score 42',
  reading_detailed: 'Dettaglio DRAW',
  input: { quota_book: 3.2, edge_pct: 5.1 },
  reason_codes: ['positive_edge'],
}

const X2_ITEM: CecchinoPurchasabilityV31Item = {
  market_key: 'X_TWO',
  market_label: 'X2',
  status: 'score_provisional',
  score: 76,
  score_v31: 76,
  class: 'Alta provvisoria',
  reading_short: 'Score 76',
  reading_detailed: 'Dettaglio X2',
  input: { quota_book: 1.45, edge_pct: 3.2 },
}

function itemsMap(...items: CecchinoPurchasabilityV31Item[]) {
  return Object.fromEntries(items.map((i) => [i.market_key, i]))
}

beforeEach(() => {
  vi.mocked(getPurchasabilityAuditExport).mockReset()
})

afterEach(() => {
  cleanup()
})

describe('CecchinoPurchasabilityPanel', () => {
  it('mostra solo mercati attivi con score', () => {
    render(
      <CecchinoPurchasabilityPanel
        version="v3.1"
        itemsByMarket={itemsMap(DRAW_ITEM, X2_ITEM, AWAY_V31_ITEM, GATE_FAILED_RATING_V31_ITEM, NON_CALCULABLE_MISSING_QUOTE_V31_ITEM)}
        snapshotAvailable
        todayFixtureId={7}
        providerFixtureId={555}
      />,
    )
    expect(screen.getAllByRole('tab')).toHaveLength(3)
    expect(screen.queryByTestId('purch-selector-HOME')).toBeNull()
    expect(screen.getByTestId('purch-selector-X_TWO')).toBeTruthy()
  })

  it('default selection = score più alto', () => {
    render(
      <CecchinoPurchasabilityPanel
        version="v3.1"
        itemsByMarket={itemsMap(DRAW_ITEM, X2_ITEM, AWAY_V31_ITEM)}
        snapshotAvailable
        todayFixtureId={7}
      />,
    )
    const x2 = screen.getByTestId('purch-selector-X_TWO')
    expect(x2.getAttribute('data-selected')).toBe('true')
    expect(screen.getByTestId('cecchino-purchasability-detail').getAttribute('data-market-key')).toBe(
      'X_TWO',
    )
  })

  it('click selector cambia dettaglio', () => {
    render(
      <CecchinoPurchasabilityPanel
        version="v3.1"
        itemsByMarket={itemsMap(DRAW_ITEM, X2_ITEM, AWAY_V31_ITEM)}
        snapshotAvailable
        todayFixtureId={7}
      />,
    )
    fireEvent.click(screen.getByTestId('purch-selector-DRAW'))
    expect(screen.getByTestId('cecchino-purchasability-detail').getAttribute('data-market-key')).toBe(
      'DRAW',
    )
  })

  it('empty state se nessun mercato attivo', () => {
    render(
      <CecchinoPurchasabilityPanel
        version="v3.1"
        itemsByMarket={itemsMap(GATE_FAILED_RATING_V31_ITEM, NON_CALCULABLE_MISSING_QUOTE_V31_ITEM)}
        snapshotAvailable
        todayFixtureId={7}
      />,
    )
    expect(screen.getByTestId('cecchino-purchasability-panel').getAttribute('data-empty')).toBe('true')
    expect(screen.getByText(/Nessuna opportunità attiva/)).toBeTruthy()
  })

  it('audit download chiama endpoint', async () => {
    vi.mocked(getPurchasabilityAuditExport).mockResolvedValue({
      contract_version: 'cecchino_purchasability_audit_export_v1',
      generated_at: '2026-08-19T10:00:00Z',
      fixture: {},
      source_versions: {},
      market_order: [],
      market_context: { BOOK: {}, CECCHINO: {} },
      markets: {},
    })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    render(
      <CecchinoPurchasabilityPanel
        version="v3.1"
        itemsByMarket={itemsMap(X2_ITEM)}
        snapshotAvailable
        todayFixtureId={7}
        providerFixtureId={555}
      />,
    )
    fireEvent.click(screen.getByTestId('purch-audit-download-btn'))
    await vi.waitFor(() => {
      expect(getPurchasabilityAuditExport).toHaveBeenCalledWith(7)
    })
    clickSpy.mockRestore()
  })
})
