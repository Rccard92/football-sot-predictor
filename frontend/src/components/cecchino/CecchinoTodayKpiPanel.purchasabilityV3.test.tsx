/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CecchinoTodayKpiPanel } from './CecchinoTodayKpiPanel'
import type { CecchinoKpiV2Panel } from '../../lib/cecchinoTodayApi'
import {
  AWAY_V3_ITEM,
  GATE_FAILED_V3_ITEM,
  MISSING_INPUTS_V3_ITEM,
  UNSUPPORTED_V3_ITEM,
  DERIVED_V3_ITEM,
  buildAwayV3Explanation,
} from './fixtures/purchasabilityV3AwayRegression'

vi.mock('../../lib/cecchinoTodayApi', async () => {
  const actual = await vi.importActual<typeof import('../../lib/cecchinoTodayApi')>(
    '../../lib/cecchinoTodayApi',
  )
  return {
    ...actual,
    getKpiExplanations: vi.fn(),
  }
})

import { getKpiExplanations } from '../../lib/cecchinoTodayApi'

const panel: CecchinoKpiV2Panel = {
  version: 'kpi_v2',
  bookmaker: { name: 'Betfair', provider_bookmaker_id: 3, provider_source: 'betfair' },
  rows: [
    {
      market_key: 'AWAY',
      segno: '2',
      label: '2',
      quota_book: 9.5,
      quota_cecchino: 5.19,
      prob_book: 0.14,
      prob_cecchino: 0.19645,
      vantaggio_prob: 0.0874,
      edge_pct: 83.04,
      score_acquisto: 0.5,
      rating: 85,
      rating_label: 'Forte',
      status: 'ok',
    },
    {
      market_key: 'HOME',
      segno: '1',
      label: '1',
      quota_book: 1.35,
      quota_cecchino: 1.67,
      prob_book: 0.74,
      prob_cecchino: 0.6,
      edge_pct: -15,
      vantaggio_prob: -0.08,
      score_acquisto: 0.1,
      rating: 40,
      rating_label: 'Debole',
      status: 'ok',
    },
  ],
}

beforeEach(() => {
  vi.mocked(getKpiExplanations).mockReset()
})

afterEach(() => {
  cleanup()
})

describe('CecchinoTodayKpiPanel purchasability V3', () => {
  it('non mostra Acq. V1.1 desktop/mobile; mostra V2 e V3', () => {
    render(
      <CecchinoTodayKpiPanel
        panel={panel}
        purchasabilityV2ByMarketKey={{
          AWAY: {
            market_key: 'AWAY',
            status: 'available',
            score: 55,
            class: 'Media',
          },
        }}
        purchasabilityObservationalV2ByMarketKey={{
          AWAY: { status: 'available', sample_size: 12, roi_pct: 0.05 },
        }}
        purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
        purchasabilityV3SnapshotAvailable
      />,
    )
    expect(screen.queryByText('Acq. V1.1')).toBeNull()
    expect(screen.queryByText('Acquistabilità V1.1')).toBeNull()
    expect(screen.getAllByText('Acq. V2').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Acq\. V3/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Candidato').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Acquistabilità V2').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Acquistabilità V3/).length).toBeGreaterThan(0)
  })

  it('mostra score V3 e chip V3 candidato', () => {
    render(
      <CecchinoTodayKpiPanel
        panel={panel}
        purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
        purchasabilityV3SnapshotAvailable
      />,
    )
    const cells = screen.getAllByTestId('purchasability-v3-cell')
    expect(cells.some((c) => c.textContent?.includes('47'))).toBe(true)
    expect(screen.getAllByText('V3 candidato').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Non validato').length).toBeGreaterThan(0)
  })

  it('gate fallito mostra Non attivato e non 0', () => {
    render(
      <CecchinoTodayKpiPanel
        panel={panel}
        purchasabilityV3ByMarketKey={{ HOME: GATE_FAILED_V3_ITEM, AWAY: AWAY_V3_ITEM }}
        purchasabilityV3SnapshotAvailable
      />,
    )
    const failed = screen
      .getAllByTestId('purchasability-v3-cell')
      .find((c) => c.getAttribute('data-v3-kind') === 'gate_failed')
    expect(failed?.textContent).toContain('Non attivato')
    expect(failed?.textContent).not.toMatch(/\b0\b/)
  })

  it('input mancanti / non supportato / snapshot assente', () => {
    const { rerender } = render(
      <CecchinoTodayKpiPanel
        panel={panel}
        purchasabilityV3ByMarketKey={{ AWAY: MISSING_INPUTS_V3_ITEM }}
        purchasabilityV3SnapshotAvailable
      />,
    )
    expect(
      screen.getAllByTestId('purchasability-v3-cell').some((c) =>
        c.textContent?.includes('Non calcolabile'),
      ),
    ).toBe(true)

    rerender(
      <CecchinoTodayKpiPanel
        panel={{
          ...panel,
          rows: [
            {
              market_key: 'OVER_1_5',
              segno: 'Over 1.5',
              label: 'Over 1.5',
              quota_book: null,
              quota_cecchino: null,
              prob_book: null,
              prob_cecchino: null,
              vantaggio_prob: null,
              edge_pct: null,
              score_acquisto: null,
              rating: null,
              rating_label: null,
              status: 'ok',
            },
          ],
        }}
        purchasabilityV3ByMarketKey={{ OVER_1_5: UNSUPPORTED_V3_ITEM }}
        purchasabilityV3SnapshotAvailable
      />,
    )
    expect(
      screen.getAllByTestId('purchasability-v3-cell').some((c) =>
        c.textContent?.includes('Non supportato'),
      ),
    ).toBe(true)

    rerender(
      <CecchinoTodayKpiPanel
        panel={panel}
        purchasabilityV3SnapshotAvailable={false}
      />,
    )
    expect(
      screen.getAllByTestId('purchasability-v3-cell').some((c) =>
        c.textContent?.includes('V3 non disponibile'),
      ),
    ).toBe(true)
  })

  it('quota derivata', () => {
    render(
      <CecchinoTodayKpiPanel
        panel={panel}
        purchasabilityV3ByMarketKey={{ AWAY: DERIVED_V3_ITEM }}
        purchasabilityV3SnapshotAvailable
      />,
    )
    expect(
      screen.getAllByText((content) => content.includes('Quota derivata')).length,
    ).toBeGreaterThan(0)
    expect(
      screen.getAllByText((content) => content.includes('Solo diagnostico')).length,
    ).toBeGreaterThan(0)
  })

  it('cella V3 e gate-failed cliccabili in analisi; lazy load', async () => {
    vi.mocked(getKpiExplanations).mockResolvedValue({
      status: 'ok',
      markets: {
        AWAY: { purchasability_v3: buildAwayV3Explanation() },
        HOME: {
          purchasability_v3: buildAwayV3Explanation({
            market_key: 'HOME',
            market_label: '1',
            status: 'partial',
            stored_result: null,
            stored_result_display: 'Indice non attivato',
            gate: {
              gate_status: 'failed_non_positive_edge',
              edge_positive: false,
              probability_advantage_positive: true,
              gate_reason_codes: ['non_positive_edge'],
            },
            final_calculation: { score: null, class: null },
            persisted_result: {
              score: null,
              gate_status: 'failed_non_positive_edge',
            },
          }),
        },
      },
      analyzable_metrics: ['purchasability_v3'],
    })

    render(
      <CecchinoTodayKpiPanel
        panel={panel}
        todayFixtureId={42}
        purchasabilityV3ByMarketKey={{
          AWAY: AWAY_V3_ITEM,
          HOME: GATE_FAILED_V3_ITEM,
        }}
        purchasabilityV3SnapshotAvailable
      />,
    )

    expect(getKpiExplanations).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Analisi formule/i }))
    expect(getKpiExplanations).toHaveBeenCalledTimes(1)

    const analyzeButtons = await screen.findAllByRole('button', {
      name: /Analizza formula: Acquistabilità v3/i,
    })
    expect(analyzeButtons.length).toBeGreaterThan(0)
    fireEvent.click(analyzeButtons[0])
    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.getByTestId('purchasability-v3-audit-view')).toBeTruthy()
  })

  it('download audit usa lo stesso lazy load', async () => {
    vi.mocked(getKpiExplanations).mockResolvedValue({
      status: 'ok',
      markets: {},
      fixture: { today_fixture_id: 1, provider_fixture_id: 99 },
    })
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })

    render(
      <CecchinoTodayKpiPanel panel={panel} todayFixtureId={7} providerFixtureId={99} />,
    )
    expect(getKpiExplanations).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Scarica audit KPI/i }))
    await vi.waitFor(() => expect(getKpiExplanations).toHaveBeenCalledTimes(1))
    await vi.waitFor(() => expect(createObjectURL).toHaveBeenCalled())
  })

  it('V2 ancora presente nei valori', () => {
    render(
      <CecchinoTodayKpiPanel
        panel={panel}
        purchasabilityV2ByMarketKey={{
          AWAY: { market_key: 'AWAY', status: 'available', score: 61, class: 'Alta' },
        }}
        purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
        purchasabilityV3SnapshotAvailable
      />,
    )
    expect(screen.getAllByText('61').length).toBeGreaterThan(0)
  })
})
