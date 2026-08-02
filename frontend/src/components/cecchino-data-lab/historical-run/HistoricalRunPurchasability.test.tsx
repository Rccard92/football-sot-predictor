/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { HistoricalRunPurchasability } from './HistoricalRunPurchasability'
import type { HistoricalRunOfficialPurchasability } from '../../../lib/cecchinoLabApi'

afterEach(() => cleanup())

function renderPurch(data: HistoricalRunOfficialPurchasability, runId = 3) {
  return render(
    <MemoryRouter>
      <HistoricalRunPurchasability data={data} runId={runId} />
    </MemoryRouter>,
  )
}

describe('HistoricalRunPurchasability V3', () => {
  it('shows unavailable CTA to purchasability replay', () => {
    renderPurch({
      status: 'unavailable',
      official_version: 'V3',
      source_type: 'historical_replay',
      replay_id: null,
      legacy_fallback_used: false,
      message: 'Acquistabilità V3 non è disponibile per questa Run.',
      cta: {
        label: 'Verifica o avvia replay Acquistabilità',
        path: '/cecchino-lab/purchasability-replay?run_id=3',
      },
    })
    expect(screen.getByTestId('purchasability-v3-unavailable').textContent).toContain(
      'Acquistabilità V3 non disponibile',
    )
    const cta = screen.getByTestId('purchasability-v3-cta')
    expect(cta.getAttribute('href')).toBe('/cecchino-lab/purchasability-replay?run_id=3')
    expect(screen.queryByText(/diagnostic_ungated/i)).toBeNull()
    expect(screen.queryByText(/V1\.1/)).toBeNull()
    expect(screen.queryByText(/\bV2\b/)).toBeNull()
  })

  it('renders official V3 summary without legacy labels', () => {
    renderPurch({
      status: 'ready_with_warnings',
      official_version: 'V3',
      source_type: 'historical_replay',
      replay_id: 1,
      replay_status: 'completed_with_warnings',
      formula_version: 'cecchino_purchasability_v3_fixed_discount_v1',
      legacy_fallback_used: false,
      results_persisted: 36488,
      evaluations_total: 36488,
      scored: 13534,
      gate_failed: 22950,
      unavailable: 4,
      real_quote_count: 22801,
      derived_quote_count: 13683,
      reconciliation_status: 'ok',
      performance_real: { stake_count: 100, profit_units: 1.5, roi_pct: 1.5 },
      performance_synthetic: { stake_count: 50, profit_units: -2, roi_pct: -4 },
      by_market: {
        HOME: {
          evaluations_total: 10,
          scored: 4,
          gate_failed: 6,
          unavailable: 0,
          real_quote: 10,
          derived_quote: 0,
        },
      },
    })
    expect(screen.getByTestId('historical-run-purchasability-v3')).toBeTruthy()
    expect(screen.getByTestId('purchasability-v3-summary').textContent).toContain('13534')
    expect(screen.getByTestId('purchasability-v3-roi-real').textContent).toContain('1.50%')
    expect(screen.getByTestId('purchasability-v3-roi-synthetic').textContent).toContain('-4.00%')
    expect(screen.queryByText(/diagnostic_ungated/i)).toBeNull()
    expect(screen.queryByText(/V1\.1/)).toBeNull()
  })
})
