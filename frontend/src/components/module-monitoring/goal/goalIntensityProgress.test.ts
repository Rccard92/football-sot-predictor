import { describe, expect, it } from 'vitest'
import {
  BENCHMARK_MODEL_ORDER,
  PHASE_2C_ACTIVE_CANDIDATES,
  PHASE_2C_ARCHIVED_CANDIDATES,
  PHASE_2C_HOLDOUT_MODELS,
  coverageCount,
  evidenceLabelIt,
  phase2cFreezeDisabled,
  progressDerived,
  resolveCompleted,
  resolveMinimum,
  resolvePending,
  resolveSnapshots,
} from './goalIntensityProgress'
import { PHASE_2C_FREEZE_CONFIRM } from '../../../lib/cecchinoGoalIntensityV5Api'

describe('goalIntensityProgress field resolution', () => {
  it('risolve completed da prospective_progress.completed', () => {
    expect(resolveCompleted({ completed: 702 }, { completed_n: 1 })).toBe(702)
  })

  it('fallback completed_n / completed_snapshots', () => {
    expect(resolveCompleted({}, { completed_n: 50 })).toBe(50)
    expect(resolveCompleted({}, { completed_snapshots: 40 })).toBe(40)
    expect(resolveCompleted({})).toBe(0)
  })

  it('risolve pending / snapshots / minimum', () => {
    expect(resolvePending({ pending: 323 }, { pending_n: 1 })).toBe(323)
    expect(resolveSnapshots({ snapshots: 1025 }, { total_snapshots: 1 })).toBe(1025)
    expect(resolveMinimum({ minimum: 200 }, {})).toBe(200)
    expect(resolveMinimum({}, { minimum_prospective_matches: 200 })).toBe(200)
    expect(resolveMinimum({})).toBe(200)
  })

  it('progress >100%, remaining zero, excess positivo', () => {
    const d = progressDerived(702, 200)
    expect(d.progress_pct).toBeCloseTo(351)
    expect(d.remaining).toBe(0)
    expect(d.excess).toBe(502)
    expect(d.minimum_reached).toBe(true)
  })

  it('coverageCount distingue global e period', () => {
    const global = { snapshots: 1025, completed: 702, pending: 323 }
    const period = { snapshots: 921, completed: 702, pending: 219 }
    expect(coverageCount(global, 'snapshots')).toBe(1025)
    expect(coverageCount(period, 'pending')).toBe(219)
    expect(coverageCount(null, 'completed')).toBeNull()
  })

  it('evidence labels neutre', () => {
    expect(evidenceLabelIt('low', 'none')).toContain('non conclusiva')
    expect(evidenceLabelIt('insufficient_sample', null)).toContain('non disponibile')
    expect(evidenceLabelIt('supported', 'left')).toContain('errore inferiore')
  })

  it('ordine modelli benchmark include cinque righe canoniche', () => {
    expect(BENCHMARK_MODEL_ORDER).toHaveLength(5)
    expect(BENCHMARK_MODEL_ORDER).toContain('GI_A_STRICT_CORE')
    expect(BENCHMARK_MODEL_ORDER).toContain('GI_B_RECENCY')
    expect(BENCHMARK_MODEL_ORDER).toContain('MT1_LONG_TERM')
    expect(BENCHMARK_MODEL_ORDER).toContain('GI_A_without_volatility')
    expect(BENCHMARK_MODEL_ORDER).toContain('GI_V4_EXPECTED_GOALS')
  })
})

describe('Phase 2C variants helpers', () => {
  it('quattro candidati attivi e due archiviati', () => {
    expect(PHASE_2C_ACTIVE_CANDIDATES).toEqual([
      'GI_A_STRICT_CORE',
      'GI_B_RECENCY',
      'GI_E_PRIMARY_RECALIBRATED',
      'GI_F_REGULARIZED_PILLARS',
    ])
    expect(PHASE_2C_ARCHIVED_CANDIDATES).toEqual([
      'MT1_LONG_TERM',
      'GI_A_without_volatility',
    ])
    expect(PHASE_2C_HOLDOUT_MODELS).toHaveLength(5)
    expect(PHASE_2C_HOLDOUT_MODELS).toContain('GI_V4_EXPECTED_GOALS')
  })

  it('freeze disabilitato se blocked o freeze_allowed false', () => {
    expect(phase2cFreezeDisabled(null)).toBe(true)
    expect(phase2cFreezeDisabled({ freeze_allowed: false })).toBe(true)
    expect(phase2cFreezeDisabled({ status: 'blocked', freeze_allowed: true })).toBe(true)
    expect(phase2cFreezeDisabled({ status: 'preview', freeze_allowed: true })).toBe(false)
  })

  it('confirm token canonico e testi non promozionali', () => {
    expect(PHASE_2C_FREEZE_CONFIRM).toBe('FREEZE_GOAL_INTENSITY_V5_CANDIDATE_BUNDLE_V2_1')
    const banned = ['modello vincente', 'giocata consigliata', 'profittevole']
    for (const w of banned) {
      expect(evidenceLabelIt('supported', 'left').toLowerCase()).not.toContain(w)
    }
  })
})
