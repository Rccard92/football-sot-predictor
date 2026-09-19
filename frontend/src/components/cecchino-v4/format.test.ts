import { describe, expect, it } from 'vitest'
import {
  digestShort,
  fmtCount,
  fmtDayLabel,
  fmtGoalsRange,
  fmtInterval,
  fmtLine,
  fmtPct,
  fmtProfit,
  fmtQuota,
  fmtRoiWithCi,
  fmtSigned,
  fmtTimeRome,
  isIsoDate,
} from './format'

describe('formattatori italiani V4', () => {
  it('quota con la virgola a due cifre', () => {
    expect(fmtQuota(1.85)).toBe('1,85')
    expect(fmtQuota(2)).toBe('2,00')
    expect(fmtQuota(null)).toBe('–')
  })

  it('percentuale intera', () => {
    expect(fmtPct(0.61)).toBe('61%')
    expect(fmtPct(0.005)).toBe('1%')
    expect(fmtPct(undefined)).toBe('–')
  })

  it('probabilita con intervallo', () => {
    expect(fmtInterval(0.61, 0.55, 0.66)).toBe('61% (55–66)')
    expect(fmtInterval(0.61, null, null)).toBe('61%')
  })

  it('profitto atteso con segno', () => {
    expect(fmtProfit(0.13)).toBe('+13%')
    expect(fmtProfit(-0.06)).toBe('−6%')
    expect(fmtProfit(0)).toBe('0%')
  })

  it('ROI con intervallo a una cifra', () => {
    expect(fmtRoiWithCi(-0.012, -0.04, 0.018)).toBe('−1,2% (−4,0 · +1,8)')
  })

  it('linea, gol attesi, conteggi, segni', () => {
    expect(fmtLine(6.5)).toBe('6,5')
    expect(fmtLine('7.5')).toBe('7,5')
    expect(fmtGoalsRange(1.2, 1.6)).toBe('1,2 - 1,6')
    expect(fmtCount(7000)).toBe('7.000')
    expect(fmtSigned(0.18)).toBe('+0,18')
    expect(fmtSigned(-0.05)).toBe('−0,05')
  })

  it('orario su Europe/Rome', () => {
    // 18:45Z del 21 settembre = 20:45 a Roma (ora legale)
    expect(fmtTimeRome('2026-09-21T18:45:00Z')).toBe('20:45')
    // 19:30Z del 15 gennaio = 20:30 a Roma (ora solare)
    expect(fmtTimeRome('2026-01-15T19:30:00Z')).toBe('20:30')
  })

  it('etichetta giorno e impronta', () => {
    expect(fmtDayLabel('2026-09-21')).toBe('lun 21/09')
    expect(digestShort('sha256:abcdef0123456789ffff')).toBe('abcdef012345…')
    expect(isIsoDate('2026-09-21')).toBe(true)
    expect(isIsoDate('21/09/2026')).toBe(false)
  })
})
