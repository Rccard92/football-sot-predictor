import { describe, expect, it } from 'vitest'
import {
  BENCHMARK_MODEL_ORDER,
  coverageCount,
  evidenceLabelIt,
  progressDerived,
  resolveCompleted,
  resolveMinimum,
  resolvePending,
  resolveSnapshots,
} from './goalIntensityProgress'

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
