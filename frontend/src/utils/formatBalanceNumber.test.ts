import { describe, expect, it } from 'vitest'
import { formatBalanceNumber } from './formatBalanceNumber'

describe('formatBalanceNumber', () => {
  it('formatta con locale it-IT e unità', () => {
    expect(formatBalanceNumber(71.22, 'index')).toBe('71,22')
    expect(formatBalanceNumber(95.3, 'index')).toBe('95,3')
    expect(formatBalanceNumber(40, 'index')).toBe('40')
    expect(formatBalanceNumber(25.31, 'pct')).toBe('25,31%')
    expect(formatBalanceNumber(16.48, 'pp')).toBe('16,48 pp')
    expect(formatBalanceNumber(2.85, 'quota')).toBe('2,85')
  })

  it('mancanti come —', () => {
    expect(formatBalanceNumber(null, 'index')).toBe('—')
    expect(formatBalanceNumber(undefined, 'pct')).toBe('—')
  })
})
