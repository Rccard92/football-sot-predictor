import { describe, expect, it } from 'vitest'
import { breakEvenQuota, marketsConflict, patternRelation } from './cecchinoPatternUtils'

describe('marketsConflict', () => {
  it('1X2 e doppia chance', () => {
    expect(marketsConflict('HOME', 'AWAY')).toBe(true)
    expect(marketsConflict('HOME', 'X_TWO')).toBe(true)
    expect(marketsConflict('HOME', 'ONE_X')).toBe(false)
    expect(marketsConflict('DRAW', 'ONE_TWO')).toBe(true)
  })
  it('primo tempo separato dal finale', () => {
    expect(marketsConflict('HOME_PT', 'AWAY')).toBe(false)
    expect(marketsConflict('HOME_PT', 'AWAY_PT')).toBe(true)
  })
  it('over e under', () => {
    expect(marketsConflict('OVER_2_5', 'UNDER_2_5')).toBe(true)
    expect(marketsConflict('UNDER_1_5', 'OVER_2_5')).toBe(true)
    expect(marketsConflict('OVER_2_5', 'UNDER_3_5')).toBe(false)
    expect(marketsConflict('OVER_1_5', 'OVER_2_5')).toBe(false)
    expect(marketsConflict('HOME', 'UNDER_2_5')).toBe(false)
  })
  it('relazione con i pattern', () => {
    expect(patternRelation('AWAY', ['AWAY'])).toBe('confirmed')
    expect(patternRelation('HOME', ['AWAY'])).toBe('conflict')
    expect(patternRelation('UNDER_3_5', ['AWAY'])).toBe(null)
    expect(breakEvenQuota(50)).toBe(2)
  })
})
