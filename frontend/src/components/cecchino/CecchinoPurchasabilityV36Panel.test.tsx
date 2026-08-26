/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CecchinoPurchasabilityV36Panel } from './CecchinoPurchasabilityV36Panel'
import {
  V36_NO_SCORE_SNAPSHOT,
  V36_VALID_SNAPSHOT,
} from './fixtures/purchasabilityV36Fixtures'
import { indexPurchasabilityV36ByMarketKey } from '../../lib/cecchinoTodayApi'
import * as api from '../../lib/cecchinoTodayApi'

vi.mock('../../lib/cecchinoTodayApi', async () => {
  const actual = await vi.importActual('../../lib/cecchinoTodayApi')
  return {
    ...actual,
    getPurchasabilityV36AuditExport: vi.fn(),
  }
})

describe('CecchinoPurchasabilityV36Panel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('renderizza detail valid V3.6 con default max raw_score', () => {
    const items = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={V36_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={items}
        todayFixtureId={1}
        providerFixtureId={100}
      />,
    )
    expect(screen.getByTestId('cecchino-purchasability-v36-panel').getAttribute('data-status')).toBe(
      'valid',
    )
    expect(screen.getByText('Indice di Acquistabilità V3.6')).toBeTruthy()
    expect(screen.getByTestId('v36-selector-DRAW').getAttribute('data-selected')).toBe('true')
    const score = screen.getByTestId('v36-final-score')
    expect(score.textContent).toBe('55 / 100')
    expect(score.textContent).not.toContain('%')
  })

  it('mercati score ordinati DESC nel selector', () => {
    const items = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={V36_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={items}
      />,
    )
    const buttons = screen.getAllByRole('tab')
    expect(buttons[0].getAttribute('data-testid')).toBe('v36-selector-DRAW')
    expect(buttons[1].getAttribute('data-testid')).toBe('v36-selector-HOME')
  })

  it('assente: messaggio corretto senza fallback V3.5', () => {
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={null}
        snapshotStatus="absent"
        itemsByMarket={{}}
      />,
    )
    expect(screen.getByTestId('v36-absent-message').textContent).toMatch(/Indice V3.6 non disponibile/)
    expect(screen.queryByText(/Acquistabilità V3\.5/)).toBeNull()
    expect(screen.queryByText('LIVE SHADOW')).toBeNull()
  })

  it('present_but_invalid: warning e reason in diagnostica', () => {
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={null}
        snapshotStatus="present_but_invalid"
        snapshotReason="formula_freeze_mismatch"
        itemsByMarket={{}}
      />,
    )
    expect(screen.getByText(/Snapshot V3.6 non valido/)).toBeTruthy()
    expect(screen.getByTestId('v36-invalid-diagnostics').textContent).toContain(
      'formula_freeze_mismatch',
    )
  })

  it('mostra R come Base-rate Reliability Index e disclaimer', () => {
    const items = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={V36_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={items}
      />,
    )
    expect(screen.getAllByText(/Base-rate Reliability Index \(R\)/).length).toBeGreaterThan(0)
    expect(screen.getByTestId('v36-r-disclaimer').textContent).toMatch(/non è una\s+probabilità calibrata/i)
    expect(screen.getByTestId('v36-header-disclaimer').textContent).toMatch(
      /Non è una probabilità calibrata di vittoria/,
    )
  })

  it('S missing mostra penalizzazione', () => {
    const items = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={V36_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={items}
      />,
    )
    fireEvent.click(screen.getByTestId('v36-selector-AWAY'))
    expect(screen.getByTestId('v36-s-missing').textContent).toMatch(/penalizzazione strutturale/)
  })

  it('mostra structural blocks e Q penalties', () => {
    const items = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={V36_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={items}
      />,
    )
    expect(screen.getByTestId('v36-block-same_family_opposition')).toBeTruthy()
    expect(screen.getByText('Opposizione stessa famiglia')).toBeTruthy()
    expect(screen.getByText('Copertura laterale')).toBeTruthy()
    expect(screen.getByTestId('v36-q-penalties').textContent).toContain('overround_penalty')
  })

  it('nessun candidate A/B/C/D e nessun testo V3.5', () => {
    const items = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={V36_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={items}
      />,
    )
    expect(screen.queryByText(/Candidate A/)).toBeNull()
    expect(screen.queryByText(/Candidate B/)).toBeNull()
    expect(screen.queryByText('LIVE SHADOW')).toBeNull()
    expect(screen.queryByText('structural_v1')).toBeNull()
    expect(screen.queryByText(/Acquistabilità V3\.5/)).toBeNull()
  })

  it('audit V3.6 chiama endpoint v35-v2', async () => {
    vi.mocked(api.getPurchasabilityV36AuditExport).mockResolvedValue({
      contract_version: 'cecchino_purchasability_v35_v2_audit_export_v1',
      generated_at: '2026-08-26T00:00:00Z',
      fixture: {},
      snapshot_identity: {},
      frozen_config: {},
      relation_registry: [],
      market_order: [],
      markets: {},
    })
    const items = indexPurchasabilityV36ByMarketKey(V36_VALID_SNAPSHOT)
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={V36_VALID_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={items}
        todayFixtureId={42}
        providerFixtureId={999}
      />,
    )
    fireEvent.click(screen.getByTestId('v36-audit-download-btn'))
    await waitFor(() => {
      expect(api.getPurchasabilityV36AuditExport).toHaveBeenCalledWith(42)
    })
    expect(screen.getByTestId('v36-audit-download-btn').textContent).toContain('Scarica audit V3.6')
  })

  it('valid no-score mostra inactive section', () => {
    const items = indexPurchasabilityV36ByMarketKey(V36_NO_SCORE_SNAPSHOT)
    render(
      <CecchinoPurchasabilityV36Panel
        snapshot={V36_NO_SCORE_SNAPSHOT}
        snapshotStatus="valid"
        itemsByMarket={items}
      />,
    )
    expect(screen.getByTestId('cecchino-purchasability-v36-panel').getAttribute('data-status')).toBe(
      'valid-no-score',
    )
    expect(screen.getByTestId('v36-inactive-markets')).toBeTruthy()
  })
})
