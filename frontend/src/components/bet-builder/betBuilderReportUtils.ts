/** Rapporti del Bet Builder (richiesta di Giovanni, 13/10/2026): stesse regole del backend
 *  (`build_results_report`): fasce di quota, ROI con forbice di incertezza al 90%, mappa del valore. */

export type RoiStat = {
  plays: number
  won: number
  win_pct: number | null
  break_even_pct: number | null
  avg_quota: number | null
  profit: number
  roi_pct: number | null
  roi_low_pct: number | null
  roi_high_pct: number | null
}

export type BandStat = RoiStat & { band: string }
export type StepStat = RoiStat & { step: string; roi_vs_baseline_pct: number | null }
export type MonthStat = RoiStat & { month: string }
export type MarketBandStat = RoiStat & { market_key: string; market_label: string; band: string; value: boolean }
export type ScoreBandStat = RoiStat & { band: string; avg_prob_pct: number | null }
export type CalibrationBin = { bin: string; plays: number; predicted_pct: number | null; actual_pct: number | null }

export type BetBuilderReport = {
  summary: RoiStat
  quota_bands: BandStat[]
  index_steps?: StepStat[]
  monthly: MonthStat[]
  market_bands: MarketBandStat[]
  score_bands?: ScoreBandStat[]
  calibration?: CalibrationBin[]
  value_rule?: string
}

export const QUOTA_BANDS: { band: string; lo: number; hi: number }[] = [
  { band: 'sotto 1,41', lo: 0, hi: 1.405 },
  { band: '1,41-1,60', lo: 1.405, hi: 1.605 },
  { band: '1,61-1,80', lo: 1.605, hi: 1.805 },
  { band: '1,81-2,00', lo: 1.805, hi: 2.005 },
  { band: '2,01-2,20', lo: 2.005, hi: 2.205 },
  { band: 'da 2,21', lo: 2.205, hi: 1e9 },
]
export const VALUE_MIN_PLAYS = 30
const Z90 = 1.645

export function quotaBand(q: number): string {
  return (QUOTA_BANDS.find((b) => q >= b.lo && q < b.hi) ?? QUOTA_BANDS[QUOTA_BANDS.length - 1]).band
}

const round1 = (v: number) => Math.round(v * 10) / 10

/** plays = [vinta, quota]. ROI e forbice al 90% sul profitto medio per giocata da 1 unita'. */
export function roiStats(plays: [boolean, number][]): RoiStat {
  const n = plays.length
  if (n === 0) {
    return { plays: 0, won: 0, win_pct: null, break_even_pct: null, avg_quota: null, profit: 0, roi_pct: null, roi_low_pct: null, roi_high_pct: null }
  }
  const profits = plays.map(([w, q]) => (w ? q - 1 : -1))
  const mean = profits.reduce((a, b) => a + b, 0) / n
  const variance = n > 1 ? profits.reduce((a, p) => a + (p - mean) ** 2, 0) / (n - 1) : 0
  const half = n > 1 ? (Z90 * Math.sqrt(variance)) / Math.sqrt(n) : null
  const won = plays.filter(([w]) => w).length
  return {
    plays: n,
    won,
    win_pct: round1((100 * won) / n),
    break_even_pct: round1((100 * plays.reduce((a, [, q]) => a + 1 / q, 0)) / n),
    avg_quota: Math.round((plays.reduce((a, [, q]) => a + q, 0) / n) * 100) / 100,
    profit: Math.round(profits.reduce((a, b) => a + b, 0) * 100) / 100,
    roi_pct: round1(100 * mean),
    roi_low_pct: half != null ? round1(100 * (mean - half)) : null,
    roi_high_pct: half != null ? round1(100 * (mean + half)) : null,
  }
}

export function isValueCell(s: RoiStat): boolean {
  return s.plays >= VALUE_MIN_PLAYS && (s.roi_low_pct ?? -1) > 0
}

/** Una giocata conclusa per i rapporti del Bet Builder V3. */
export type ReportPlay = {
  won: boolean
  quota: number
  marketKey: string
  marketLabel: string
  scanDate: string
  score: number | null
  winProb: number | null
}

export function buildV3Report(plays: ReportPlay[]): BetBuilderReport {
  const pairs = (xs: ReportPlay[]): [boolean, number][] => xs.map((p) => [p.won, p.quota])
  const quota_bands = QUOTA_BANDS.map(({ band }) => ({ band, ...roiStats(pairs(plays.filter((p) => quotaBand(p.quota) === band))) }))

  const byMonth = new Map<string, ReportPlay[]>()
  for (const p of plays) {
    const m = p.scanDate.slice(0, 7)
    byMonth.set(m, [...(byMonth.get(m) ?? []), p])
  }
  const monthly = [...byMonth.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([month, xs]) => ({ month, ...roiStats(pairs(xs)) }))

  const cells = new Map<string, ReportPlay[]>()
  for (const p of plays) {
    const k = `${p.marketKey}|${quotaBand(p.quota)}`
    cells.set(k, [...(cells.get(k) ?? []), p])
  }
  const market_bands = [...cells.entries()].map(([k, xs]) => {
    const [market_key, band] = k.split('|')
    const s = roiStats(pairs(xs))
    return { ...s, market_key, market_label: xs[0].marketLabel, band, value: isValueCell(s) }
  })

  const SCORE_BANDS: { band: string; lo: number; hi: number }[] = [
    { band: '70-79', lo: 70, hi: 80 },
    { band: '80-89', lo: 80, hi: 90 },
    { band: '90-99', lo: 90, hi: 99.95 },
    { band: '100', lo: 99.95, hi: 1e9 },
  ]
  const score_bands = SCORE_BANDS.map(({ band, lo, hi }) => {
    const xs = plays.filter((p) => p.score != null && p.score >= lo && p.score < hi)
    const probs = xs.map((p) => p.winProb).filter((v): v is number => v != null)
    return {
      band,
      ...roiStats(pairs(xs)),
      avg_prob_pct: probs.length ? round1((100 * probs.reduce((a, b) => a + b, 0)) / probs.length) : null,
    }
  })

  const calibration: CalibrationBin[] = []
  for (let lo = 0; lo < 100; lo += 10) {
    const xs = plays.filter((p) => p.winProb != null && p.winProb * 100 >= lo && p.winProb * 100 < lo + 10)
    if (!xs.length) continue
    calibration.push({
      bin: `${lo}-${lo + 10}%`,
      plays: xs.length,
      predicted_pct: round1((100 * xs.reduce((a, p) => a + (p.winProb ?? 0), 0)) / xs.length),
      actual_pct: round1((100 * xs.filter((p) => p.won).length) / xs.length),
    })
  }

  return {
    summary: roiStats(pairs(plays)),
    quota_bands,
    monthly,
    market_bands,
    score_bands,
    calibration,
    value_rule: `valore = almeno ${VALUE_MIN_PLAYS} giocate e ROI positivo anche nel caso peggiore della forbice al 90%`,
  }
}
