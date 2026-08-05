/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CecchinoTodayKpiPanel } from './CecchinoTodayKpiPanel'
import type { CecchinoKpiV2Panel } from '../../lib/cecchinoTodayApi'
import {
  AWAY_V31_ITEM,
  GATE_FAILED_RATING_V31_ITEM,
  NON_CALCULABLE_MISSING_QUOTE_V31_ITEM,
  buildAwayV31Explanation,
  buildGateFailedV31Explanation,
} from './fixtures/purchasabilityV31Fixtures'
import {
  AWAY_V3_ITEM,
  GATE_FAILED_V3_ITEM,
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

describe('CecchinoTodayKpiPanel purchasability V3.1', () => {
  describe('selettore versione', () => {
    it('mostra selettore quando V3.1 disponibile', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
          purchasabilityV3SnapshotAvailable
          purchasabilityV31ByMarketKey={{ AWAY: AWAY_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      expect(screen.getAllByTestId('purchasability-version-selector').length).toBeGreaterThan(0)
      expect(screen.getAllByTestId('purchasability-version-v3').length).toBeGreaterThan(0)
      expect(screen.getAllByTestId('purchasability-version-v31').length).toBeGreaterThan(0)
    })

    it('non mostra selettore quando V3.1 non disponibile', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
          purchasabilityV3SnapshotAvailable
        />,
      )
      expect(screen.queryByTestId('purchasability-version-selector')).toBeNull()
    })

    it('default è V3', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
          purchasabilityV3SnapshotAvailable
          purchasabilityV31ByMarketKey={{ AWAY: AWAY_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      const v3Btns = screen.getAllByTestId('purchasability-version-v3')
      expect(v3Btns[0].getAttribute('aria-checked')).toBe('true')
      expect(screen.getAllByTestId('purchasability-v3-cell').length).toBeGreaterThan(0)
    })

    it('switch a V3.1 cambia le celle', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
          purchasabilityV3SnapshotAvailable
          purchasabilityV31ByMarketKey={{ AWAY: AWAY_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      expect(v31Btns[0].getAttribute('aria-checked')).toBe('true')
      expect(screen.getAllByTestId('purchasability-v31-cell').length).toBeGreaterThan(0)
    })

    it('switch non modifica altre colonne', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
          purchasabilityV3SnapshotAvailable
          purchasabilityV31ByMarketKey={{ AWAY: AWAY_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      const quotaBefore = screen.getAllByText('9.50')
      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      const quotaAfter = screen.getAllByText('9.50')
      expect(quotaBefore.length).toBe(quotaAfter.length)
    })
  })

  describe('celle V3.1', () => {
    it('mostra score con badge "V3.1 shadow"', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV31ByMarketKey={{ AWAY: AWAY_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      const cells = screen.getAllByTestId('purchasability-v31-cell')
      const scoreCell = cells.find((c) => c.getAttribute('data-v31-kind') === 'score')
      expect(scoreCell?.textContent).toContain('52')
      expect(scoreCell?.textContent).toContain('V3.1 shadow')
    })

    it('gate fallito mostra "Non attivato" con motivo', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV31ByMarketKey={{ HOME: GATE_FAILED_RATING_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      const cells = screen.getAllByTestId('purchasability-v31-cell')
      const failedCell = cells.find((c) => c.getAttribute('data-v31-kind') === 'gate_failed')
      expect(failedCell?.textContent).toContain('Non attivato')
      expect(failedCell?.textContent).toContain('Rating sotto 50')
    })

    it('non calcolabile mostra "Non calcolabile" con motivo', () => {
      render(
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
          purchasabilityV31ByMarketKey={{ OVER_1_5: NON_CALCULABLE_MISSING_QUOTE_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      const cells = screen.getAllByTestId('purchasability-v31-cell')
      const nonCalcCell = cells.find((c) => c.getAttribute('data-v31-kind') === 'non_calculable')
      expect(nonCalcCell?.textContent).toContain('Non calcolabile')
      expect(nonCalcCell?.textContent).toContain('Quota mancante')
    })

    it('stato loading mostra "Calcolo in corso…"', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV31Loading
          purchasabilityV31SnapshotAvailable={false}
        />,
      )
      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      const cells = screen.getAllByTestId('purchasability-v31-cell')
      expect(cells.some((c) => c.textContent?.includes('Calcolo in corso'))).toBe(true)
    })
  })

  describe('mobile view', () => {
    it('selettore versione in vista mobile', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
          purchasabilityV3SnapshotAvailable
          purchasabilityV31ByMarketKey={{ AWAY: AWAY_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      const selectors = screen.getAllByTestId('purchasability-version-selector')
      expect(selectors.length).toBeGreaterThan(0)
    })
  })

  describe('analisi formule V3.1', () => {
    it('cella V3.1 cliccabile in analisi quando analyzable', async () => {
      vi.mocked(getKpiExplanations).mockResolvedValue({
        status: 'ok',
        markets: {
          AWAY: {
            purchasability_v31: buildAwayV31Explanation(),
          },
          HOME: {
            purchasability_v31: buildGateFailedV31Explanation(),
          },
        },
        analyzable_metrics: ['purchasability_v31'],
      })

      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          todayFixtureId={42}
          purchasabilityV31ByMarketKey={{
            AWAY: AWAY_V31_ITEM,
            HOME: GATE_FAILED_RATING_V31_ITEM,
          }}
          purchasabilityV31SnapshotAvailable
        />,
      )

      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      fireEvent.click(screen.getByRole('button', { name: /Analisi formule/i }))
      await vi.waitFor(() => expect(getKpiExplanations).toHaveBeenCalled())

      const analyzeButtons = await screen.findAllByRole('button', {
        name: /Analizza formula: Acquistabilità$/i,
      })
      expect(analyzeButtons.length).toBeGreaterThan(0)
      fireEvent.click(analyzeButtons[0])
      expect(await screen.findByRole('dialog')).toBeTruthy()
      expect(screen.getByTestId('purchasability-v31-audit-view')).toBeTruthy()
      expect(screen.getByText('Analisi Acquistabilità V3.1')).toBeTruthy()
    })

    it('gate_failed analyzable anche con score null', async () => {
      vi.mocked(getKpiExplanations).mockResolvedValue({
        status: 'ok',
        markets: {
          HOME: {
            purchasability_v31: buildGateFailedV31Explanation(),
          },
        },
        analyzable_metrics: ['purchasability_v31'],
      })

      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          todayFixtureId={42}
          purchasabilityV31ByMarketKey={{
            HOME: GATE_FAILED_RATING_V31_ITEM,
          }}
          purchasabilityV31SnapshotAvailable
        />,
      )

      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      fireEvent.click(screen.getByRole('button', { name: /Analisi formule/i }))
      await vi.waitFor(() => expect(getKpiExplanations).toHaveBeenCalled())

      const analyzeButtons = await screen.findAllByRole('button', {
        name: /Analizza formula: Acquistabilità$/i,
      })
      expect(analyzeButtons.length).toBeGreaterThan(0)
    })
  })

  describe('compatibilità V3', () => {
    it('V3 test esistenti non rompono', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM, HOME: GATE_FAILED_V3_ITEM }}
          purchasabilityV3SnapshotAvailable
        />,
      )
      const cells = screen.getAllByTestId('purchasability-v3-cell')
      expect(cells.some((c) => c.textContent?.includes('47'))).toBe(true)
    })

    it('switch da V31 a V3 mostra celle V3', () => {
      render(
        <CecchinoTodayKpiPanel
          panel={panel}
          purchasabilityV3ByMarketKey={{ AWAY: AWAY_V3_ITEM }}
          purchasabilityV3SnapshotAvailable
          purchasabilityV31ByMarketKey={{ AWAY: AWAY_V31_ITEM }}
          purchasabilityV31SnapshotAvailable
        />,
      )
      const v31Btns = screen.getAllByTestId('purchasability-version-v31')
      fireEvent.click(v31Btns[0])
      expect(screen.getAllByTestId('purchasability-v31-cell').length).toBeGreaterThan(0)
      const v3Btns = screen.getAllByTestId('purchasability-version-v3')
      fireEvent.click(v3Btns[0])
      expect(screen.getAllByTestId('purchasability-v3-cell').length).toBeGreaterThan(0)
    })
  })
})
