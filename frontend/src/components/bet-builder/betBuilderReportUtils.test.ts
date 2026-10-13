import { describe, expect, it } from 'vitest'
import { buildV3Report, isValueCell, quotaBand, roiStats, type ReportPlay } from './betBuilderReportUtils'

describe('rapporti Bet Builder (13/10/2026)', () => {
  it('fasce di quota come le ha chieste Giovanni', () => {
    expect([1.4, 1.41, 1.6, 1.61, 2, 2.2, 2.21].map(quotaBand)).toEqual([
      'sotto 1,41',
      '1,41-1,60',
      '1,41-1,60',
      '1,61-1,80',
      '1,81-2,00',
      '2,01-2,20',
      'da 2,21',
    ])
  })

  it('ROI, pareggio e forbice al 90%', () => {
    const s = roiStats([
      [true, 2],
      [false, 2],
      [true, 2],
      [false, 2],
    ])
    expect(s.win_pct).toBe(50)
    expect(s.break_even_pct).toBe(50)
    expect(s.roi_pct).toBe(0)
    expect(s.roi_low_pct).toBeLessThan(0)
    expect(s.roi_high_pct).toBeGreaterThan(0)
    expect(isValueCell(s)).toBe(false)
  })

  it('valore solo con almeno 30 giocate e caso peggiore positivo', () => {
    const many: [boolean, number][] = Array.from({ length: 60 }, (_, i) => [i % 4 !== 0, 2])
    expect(isValueCell(roiStats(many))).toBe(true)
    expect(isValueCell(roiStats(many.slice(0, 20)))).toBe(false)
  })

  it('report V3: punteggio, calibrazione e mesi', () => {
    const p = (won: boolean, score: number, prob: number, date: string): ReportPlay => ({
      won,
      quota: 1.9,
      marketKey: 'OVER_2_5',
      marketLabel: 'Over 2.5',
      scanDate: date,
      score,
      winProb: prob,
    })
    const r = buildV3Report([p(true, 100, 0.55, '2026-09-20'), p(false, 75, 0.52, '2026-10-02'), p(true, 82, 0.58, '2026-10-03')])
    expect(r.summary.plays).toBe(3)
    expect(r.score_bands?.find((b) => b.band === '100')?.plays).toBe(1)
    expect(r.calibration?.map((c) => c.bin)).toEqual(['50-60%'])
    expect(r.calibration?.[0].actual_pct).toBe(66.7)
    expect(r.monthly.map((m) => m.month)).toEqual(['2026-09', '2026-10'])
    expect(r.market_bands).toHaveLength(1)
  })
})
