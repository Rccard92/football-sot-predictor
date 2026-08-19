/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { CecchinoPurchasabilityV35Panel } from './CecchinoPurchasabilityV35Panel'
import {
  V35_NO_SCORE_SNAPSHOT,
  V35_VALID_SNAPSHOT,
} from './fixtures/purchasabilityV35Fixtures'
import { indexPurchasabilityV35ByMarketKey } from '../../lib/cecchinoTodayApi'

vi.mock('../../lib/cecchinoTodayApi', async () => {
  const actual = await vi.importActual<typeof import('../../lib/cecchinoTodayApi')>(
    '../../lib/cecchinoTodayApi',
  )
  return {
    ...actual,
    getPurchasabilityV35AuditExport: vi.fn(),
  }
})

import { getPurchasabilityV35AuditExport } from '../../lib/cecchinoTodayApi'

const validItems = indexPurchasabilityV35ByMarketKey(V35_VALID_SNAPSHOT)
const noScoreItems = indexPurchasabilityV35ByMarketKey(V35_NO_SCORE_SNAPSHOT)

beforeEach(() => {
  vi.mocked(getPurchasabilityV35AuditExport).mockReset()
})

afterEach(() => {
  cleanup()
})

describe('CecchinoPurchasabilityV35Panel', () => {
  it('A. valid snapshot con opportunity — panel render', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
        todayFixtureId={7}
        providerFixtureId={999}
      />,
    )
    expect(screen.getByTestId('cecchino-purchasability-v35-panel').getAttribute('data-status')).toBe('valid')
    expect(screen.getByTestId('v35-selector-HOME')).toBeTruthy()
  })

  it('B. valid snapshot senza score — empty-valid message', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_NO_SCORE_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={noScoreItems}
      />,
    )
    expect(screen.getByText(/Nessun mercato supera il gate V3.5/)).toBeTruthy()
  })

  it('C. unavailable — snapshot unavailable message', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={null}
        snapshotStatus="unavailable"
        itemsByMarket={{}}
      />,
    )
    expect(screen.getByText(/Snapshot V3.5 non disponibile/)).toBeTruthy()
  })

  it('D. invalid — snapshot invalid message', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={null}
        snapshotStatus="invalid"
        snapshotReason="engine_payload_sha256_mismatch"
        itemsByMarket={{}}
      />,
    )
    expect(screen.getByText(/Snapshot V3.5 non valido/)).toBeTruthy()
  })

  it('E. badge LIVE SHADOW', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
      />,
    )
    expect(screen.getByTestId('v35-live-shadow-badge').textContent).toBe('LIVE SHADOW')
    expect(screen.getByTestId('v35-formula-badge').textContent).toBe('structural_v1')
  })

  it('F/G. A REFERENCE e B/C/D TEST', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
      />,
    )
    expect(screen.getByTestId('v35-candidate-A').getAttribute('data-badge')).toBe('REFERENCE')
    expect(screen.getByTestId('v35-candidate-B').getAttribute('data-badge')).toBe('TEST')
    expect(screen.getByTestId('v35-candidate-C').getAttribute('data-badge')).toBe('TEST')
    expect(screen.getByTestId('v35-candidate-D').getAttribute('data-badge')).toBe('TEST')
  })

  it('H. cambio candidate cambia score visualizzato senza cambiare V/D/S/Q', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
      />,
    )
    expect(screen.getByTestId('v35-selected-score').textContent).toBe('63')
    fireEvent.click(screen.getByTestId('v35-candidate-D'))
    expect(screen.getByTestId('v35-selected-score').textContent).toBe('69')
    expect(screen.getByTestId('v35-comp-score-V').textContent).toBe('50.3')
  })

  it('I. score bassi status=score visibili', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
      />,
    )
    const drawTab = screen.getByTestId('v35-selector-DRAW')
    expect(drawTab.getAttribute('data-score')).toBe('8')
  })

  it('J. tabella A/B/C/D', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
      />,
    )
    expect(screen.getByTestId('v35-candidate-comparison')).toBeTruthy()
    expect(screen.getByTestId('v35-compare-row-A').getAttribute('data-highlighted')).toBe('true')
  })

  it('K. Structural detail raw/confidence/coverage', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
      />,
    )
    fireEvent.click(screen.getByTestId('v35-selector-HOME'))
    const relations = screen.getByTestId('v35-s-relations')
    expect(within(relations).getByText(/ONE_X/)).toBeTruthy()
  })

  it('L. Q penalties', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
      />,
    )
    expect(screen.getByTestId('v35-q-breakdown')).toBeTruthy()
  })

  it('M. technical details closed by default', () => {
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
      />,
    )
    const details = screen.getByTestId('v35-technical-details') as HTMLDetailsElement
    expect(details.open).toBe(false)
  })

  it('single audit click — endpoint V35', async () => {
    vi.mocked(getPurchasabilityV35AuditExport).mockResolvedValue({
      contract_version: 'cecchino_purchasability_v35_audit_export_v1',
      generated_at: '2026-08-19T10:00:00Z',
      fixture: {},
      snapshot_identity: {},
      frozen_config: {},
      candidate_registry: {},
      relation_registry: [],
      market_order: [],
      markets: {},
    })
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
        todayFixtureId={7}
        providerFixtureId={999}
      />,
    )
    fireEvent.click(screen.getByTestId('v35-audit-download-btn'))
    await vi.waitFor(() => {
      expect(getPurchasabilityV35AuditExport).toHaveBeenCalledWith(7)
    })
  })

  it('audit error state', async () => {
    vi.mocked(getPurchasabilityV35AuditExport).mockRejectedValue(new Error('fail'))
    render(
      <CecchinoPurchasabilityV35Panel
        snapshot={V35_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={validItems}
        todayFixtureId={7}
      />,
    )
    fireEvent.click(screen.getByTestId('v35-audit-download-btn'))
    await vi.waitFor(() => {
      expect(screen.getByText('Impossibile scaricare l\'audit V3.5.')).toBeTruthy()
    })
  })
})
