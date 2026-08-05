/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { CecchinoTodayKpiPanel } from './CecchinoTodayKpiPanel'
import type {
  CecchinoKpiExplanation,
  CecchinoKpiExplanationsResponse,
  CecchinoKpiV2Panel,
} from '../../lib/cecchinoTodayApi'

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

function goalRow(market_key: string, label: string, qc: number | null = 2.5) {
  return {
    market_key,
    segno: label,
    label,
    quota_book: 2.8,
    quota_cecchino: qc,
    prob_book: qc ? 1 / 2.8 : null,
    prob_cecchino: qc ? 1 / qc : null,
    vantaggio_prob: qc ? 1 / qc - 1 / 2.8 : null,
    edge_pct: qc ? ((2.8 / qc - 1) * 100) : null,
    score_acquisto: 0.1,
    rating: 55,
    rating_label: 'Media',
    status: qc ? 'ok' : 'insufficient_data',
  }
}

const panel: CecchinoKpiV2Panel = {
  version: 'kpi_v2',
  bookmaker: { name: 'Betfair', provider_bookmaker_id: 3, provider_source: 'betfair' },
  rows: [
    goalRow('HOME_PT', '1 PT'),
    goalRow('DRAW_PT', 'X PT'),
    goalRow('AWAY_PT', '2 PT'),
    goalRow('UNDER_1_5', 'Under 1.5'),
    goalRow('OVER_3_5', 'Over 3.5'),
    goalRow('UNDER_PT_0_5', 'Under PT 0.5'),
    goalRow('OVER_1_5', 'Over 1.5'),
  ],
}

function baseExplanation(
  market_key: string,
  market_label: string,
  extra: Partial<CecchinoKpiExplanation> = {},
): CecchinoKpiExplanation {
  return {
    module: 'kpi',
    market_key,
    market_label,
    metric_key: 'quota_cecchino',
    metric_label: 'Quota Cecchino',
    status: 'available',
    description: 'Quota Cecchino mercati goal / PT dal blocco goal_markets persistito.',
    purpose: 'Quota modello goal senza ricostruire lo storico.',
    formula_symbolic: 'λ → Poisson → empirico → blend → odd',
    formula_applied: [`formula_version = goal_market_poisson_empirical_v2`],
    inputs: [
      {
        key: 'event_definition',
        label: 'Definizione evento',
        value: 'test event',
        display_value: 'test event',
        source_path: `goal_markets[${market_key}].event_definition`,
      },
    ],
    stored_result: 2.5,
    stored_result_display: '2.50',
    audit_result: 2.5,
    consistency: { status: 'match', delta: 0 },
    formula_version: 'goal_market_poisson_empirical_v2',
    warnings: [],
    ...extra,
  }
}

function buildResponse(): CecchinoKpiExplanationsResponse {
  const markets: CecchinoKpiExplanationsResponse['markets'] = {}
  for (const row of panel.rows || []) {
    const mk = row.market_key
    const isFamily = mk === 'HOME_PT' || mk === 'DRAW_PT' || mk === 'AWAY_PT'
    markets[mk] = {
      quota_cecchino: baseExplanation(mk, row.label || mk, {
        formula_version: isFamily
          ? 'first_half_1x2_empirical_shrinkage_v2'
          : 'goal_market_poisson_empirical_v2',
        event_definition: isFamily
          ? 'home goals HT vs away goals HT'
          : 'FT/HT goals event',
        complementary_market: mk === 'UNDER_1_5' ? 'OVER_1_5' : undefined,
        family: isFamily
          ? {
              final_vector: { HOME_PT: 0.33, DRAW_PT: 0.34, AWAY_PT: 0.33 },
              sum_raw: 1,
              sum_check: { ok: true, sum: 1 },
            }
          : undefined,
      }),
    }
  }
  markets.UNDER_1_5_MISSING = {
    quota_cecchino: {
      ...baseExplanation('UNDER_1_5_MISSING', 'Under missing'),
      status: 'unavailable',
      stored_result: null,
      unavailable_reason: 'formula assente nello snapshot (blocco goal_markets mancante)',
      formula_applied: [],
      inputs: [],
    },
  }
  return {
    status: 'ok',
    markets,
    audit_version: 'cecchino_kpi_explanations_v1',
  }
}

beforeEach(() => {
  vi.mocked(getKpiExplanations).mockReset()
  vi.mocked(getKpiExplanations).mockResolvedValue(buildResponse())
})

afterEach(() => {
  cleanup()
})

async function activateAnalysis() {
  render(
    <CecchinoTodayKpiPanel
      panel={panel}
      todayFixtureId={42}
      purchasabilityV3ByMarketKey={{}}
      purchasabilityV3SnapshotAvailable={false}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: /Analisi formule/i }))
  await waitFor(() => {
    expect(getKpiExplanations).toHaveBeenCalled()
  })
  await waitFor(() => {
    expect(screen.getByText(/Analisi attiva/i)).toBeTruthy()
  })
}

function clickFirst(name: RegExp) {
  const buttons = screen.getAllByRole('button', { name })
  fireEvent.click(buttons[0])
}

describe('Analisi formule Fase 1B — mercati goal/PT', () => {
  it('click Quota Cecchino 1 PT apre dettaglio famiglia', async () => {
    await activateAnalysis()
    clickFirst(/Analizza formula:.*1 PT · Quota Cecchino/i)
    expect(screen.getByText(/Analisi formula/i)).toBeTruthy()
    expect(screen.getByText(/Famiglia 1X2 PT/i)).toBeTruthy()
    expect(screen.getByText(/first_half_1x2_empirical_shrinkage_v2/i)).toBeTruthy()
  })

  it('click X PT e 2 PT aprono analisi', async () => {
    await activateAnalysis()
    clickFirst(/Analizza formula:.*X PT · Quota Cecchino/i)
    expect(screen.getByText(/Famiglia 1X2 PT/i)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Chiudi/i }))
    clickFirst(/Analizza formula:.*2 PT · Quota Cecchino/i)
    expect(screen.getByText(/Famiglia 1X2 PT/i)).toBeTruthy()
  })

  it('click Under 1.5 mostra mercato opposto', async () => {
    await activateAnalysis()
    clickFirst(/Analizza formula:.*Under 1\.5 · Quota Cecchino/i)
    expect(screen.getByText(/Mercato opposto/i)).toBeTruthy()
    expect(screen.getByText('OVER_1_5')).toBeTruthy()
  })

  it('click Over 3.5 e Under PT 0.5 aprono dettaglio', async () => {
    await activateAnalysis()
    clickFirst(/Analizza formula:.*Over 3\.5 · Quota Cecchino/i)
    expect(screen.getByText(/Analisi formula/i)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Chiudi/i }))
    clickFirst(/Analizza formula:.*Under PT 0\.5 · Quota Cecchino/i)
    expect(screen.getByText(/Analisi formula/i)).toBeTruthy()
  })

  it('payload senza family (Over 1.5) non mostra famiglia e non crasha', async () => {
    await activateAnalysis()
    clickFirst(/Analizza formula:.*Over 1\.5 · Quota Cecchino/i)
    expect(screen.getAllByText(/Analisi formula/i).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Famiglia 1X2 PT/i)).toBeNull()
    expect(screen.getAllByText(/goal_market_poisson_empirical_v2/i).length).toBeGreaterThan(0)
  })

  it('motivo non calcolabile dati insufficienti è leggibile', async () => {
    const resp = buildResponse()
    resp.markets.UNDER_PT_0_5 = {
      quota_cecchino: {
        ...baseExplanation('UNDER_PT_0_5', 'Under PT 0.5'),
        status: 'unavailable',
        stored_result: null,
        stored_result_display: '—',
        unavailable_reason: 'dati insufficienti',
        formula_applied: ['status campione = insufficient_data'],
      },
    }
    vi.mocked(getKpiExplanations).mockResolvedValue(resp)
    await activateAnalysis()
    clickFirst(/Analizza formula:.*Under PT 0\.5 · Quota Cecchino/i)
    expect(screen.getByText(/dati insufficienti/i)).toBeTruthy()
  })

  it('chiusura modal e cambio selezione', async () => {
    await activateAnalysis()
    clickFirst(/Analizza formula:.*1 PT · Quota Cecchino/i)
    expect(screen.getByText(/Famiglia 1X2 PT/i)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Chiudi/i }))
    expect(screen.queryByText(/Famiglia 1X2 PT/i)).toBeNull()
    clickFirst(/Analizza formula:.*Under 1\.5 · Quota Cecchino/i)
    expect(screen.getByText(/Mercato opposto/i)).toBeTruthy()
  })
})
