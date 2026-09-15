/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { LiveModelPrediction, LivePatternSignal } from '../../lib/cecchinoLiveApi'
import { CecchinoPurchasabilityIndexV25, indexClassLabel } from './CecchinoPurchasabilityIndexV25'

function market(score: number, quota: number | null, probability = 0.46, base = 0.27) {
  return { probability, base_rate: base, score, is_prediction: score >= 70, quota, min_quota: 1 / probability, playable: score >= 70 && quota != null && quota >= 1.5 }
}

function pattern(target_key: string, uses_book = false): LivePatternSignal {
  return {
    id: 1, target_type: 'market', target_key, threshold: null, direction: 1, market_label: target_key, conditions_text: '',
    total_n: 100, win_rate_pct: 55, roi_pct: 5, avg_quota: 2, avg_deviation_pct: null, quota_book: 2, uses_book,
  }
}

function prediction(predictions: string[], active: LivePatternSignal[] = []): LiveModelPrediction {
  return {
    model: 'V2.5',
    status: 'preview',
    source: 'anteprima',
    modules: {
      patterns: { status: 'ok', active },
      purchasability_index: {
        status: 'ok',
        prediction_min_score: 70,
        playable_min_quota: 1.5,
        predictions,
        markets: { DRAW: market(82, 3.2), OVER_2_5: market(74, 1.4, 0.64, 0.5), HOME: market(40, 2.1, 0.3, 0.43) },
      },
    },
  }
}

describe('CecchinoPurchasabilityIndexV25', () => {
  afterEach(() => cleanup())

  it('mostra le predizioni con punteggio e conferma solo dai pattern senza quota', () => {
    render(<CecchinoPurchasabilityIndexV25 p={prediction(['DRAW', 'OVER_2_5'], [pattern('DRAW'), pattern('UNDER_2_5', true)])} />)
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual([expect.stringContaining('82 / 100'), expect.stringContaining('74 / 100')])
    expect(tabs[0].textContent).toContain('Confermata dal pattern')
    // il pattern sull'Under usa la quota come condizione: non conta come contrasto
    expect(tabs[1].textContent).not.toContain('In contrasto')
    expect(screen.queryByText(/non ancora in profitto/i)).toBeNull()
  })

  it('senza predizioni forti lo dice e lascia gli altri mercati', () => {
    render(<CecchinoPurchasabilityIndexV25 p={prediction([])} />)
    expect(screen.getByText(/Nessuna predizione forte/)).toBeTruthy()
    expect(screen.getByText('Altri mercati')).toBeTruthy()
  })

  it('classi del punteggio', () => {
    expect([85, 72, 65, 55, 20].map(indexClassLabel)).toEqual(['Molto Alta', 'Alta', 'Media', 'Bassa', 'Molto Bassa'])
  })
})
