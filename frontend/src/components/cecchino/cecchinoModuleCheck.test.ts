import { describe, expect, it } from 'vitest'
import type { LiveModelPrediction } from '../../lib/cecchinoLiveApi'
import { moduleVerdict } from './cecchinoModuleCheck'

function market(probability: number, edge_pct: number) {
  return { probability, edge_pct, quota_cecchino: null, quota_book: null, rating: null, vantaggio_prob: null }
}

function prediction(overrides: Partial<LiveModelPrediction> = {}): LiveModelPrediction {
  return {
    model: 'V2.5',
    status: 'preview',
    source: 'anteprima',
    markets: {
      HOME: market(0.25, -8),
      DRAW: market(0.27, -3),
      AWAY: market(0.48, 4),
      OVER_2_5: market(0.55, 2),
      UNDER_2_5: market(0.45, -9),
    },
    modules: {
      balance_classes: { draw_credibility: 'low', gap_coherence: 'confirmed' },
      goal_intensity_final: 'high',
    },
    ...overrides,
  }
}

describe('moduleVerdict', () => {
  it('pattern sul 2 confermato dai moduli', () => {
    const v = moduleVerdict(prediction(), 'AWAY')
    expect(v.key).toBe('confirmed')
    expect(v.checks.map((c) => c.outcome)).toEqual([1, 1, 1, 1])
  })

  it('pattern sull1 smentito dai moduli', () => {
    const p = prediction({ modules: { balance_classes: { draw_credibility: 'medium', gap_coherence: 'partial' } } })
    expect(moduleVerdict(p, 'HOME').key).toBe('denied')
  })

  it('under con intensità goal alta e valore negativo: smentito', () => {
    expect(moduleVerdict(prediction(), 'UNDER_2_5').key).toBe('denied')
  })

  it('V3: classi italiane', () => {
    const p = prediction({ modules: { indices: { intensita_goal: { class: 'molto_basso' } } } })
    const v = moduleVerdict(p, 'OVER_2_5')
    expect(v.key).toBe('mixed')
  })

  it('senza dati: nessuna indicazione', () => {
    expect(moduleVerdict(undefined, 'HOME').key).toBe('neutral')
  })
})
