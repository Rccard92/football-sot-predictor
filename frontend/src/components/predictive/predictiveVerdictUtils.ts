import type {
  V31CalibrationSimulator,
  V31CalibrationSimulatorStrategy,
  V31PatternAnalysis,
  V31PatternStrategyBlock,
  V31Top3FixtureComparison,
  V31WinQuality,
} from '../../lib/api'

export const TOP3_CLUSTER_UI_ORDER = [
  'all_understate_high_non_extreme',
  'dynamic_guard_improves_bias',
  'dynamic_guard_worsens_bias',
  'chaos_catches_high_non_extreme',
  'chaos_false_positive',
  'extreme_do_not_calibrate',
  'all_three_close',
  'all_three_miss',
  'bias_corrected_best',
] as const

export const CLUSTER_LABELS_IT: Record<string, string> = {
  all_understate_high_non_extreme: 'Tutti sottostimano high non estrema',
  dynamic_guard_improves_bias: 'Dynamic guard migliora bias corrected',
  dynamic_guard_worsens_bias: 'Dynamic guard peggiora bias corrected',
  chaos_catches_high_non_extreme: 'Chaos intercetta high non estrema',
  chaos_false_positive: 'Chaos false positive',
  extreme_do_not_calibrate: 'Evento estremo: non calibrare',
  all_three_close: 'Tutti e 3 vicini',
  all_three_miss: 'Tutti e 3 sbagliano',
  bias_corrected_best: 'Bias corrected migliore',
  chaos_intercepts_outlier_only: 'Chaos intercetta solo outlier',
}

export const CLUSTER_INTERPRETATION_IT: Record<string, string> = {
  all_understate_high_non_extreme:
    'Problema strutturale: partite alte ma non estreme sottostimate da tutti i modelli.',
  dynamic_guard_improves_bias: 'Il boost ibrido aiuta su queste fixture rispetto alla baseline.',
  dynamic_guard_worsens_bias: 'Il boost ibrido peggiora la baseline: serve maggiore selettività.',
  chaos_catches_high_non_extreme: 'Chaos game intercetta profili alti non outlier.',
  chaos_false_positive: 'Chaos spinge troppo alto su partite normali.',
  extreme_do_not_calibrate: 'Outlier oltre p95: studiare ma non inseguire con boost generalizzati.',
  all_three_close: 'Previsioni vicine al reale per tutti e tre i modelli.',
  all_three_miss: 'Errore elevato su tutti i modelli.',
  bias_corrected_best: 'La baseline numerica resta la più affidabile su questa fixture.',
  chaos_intercepts_outlier_only: 'Chaos migliora su outlier ma resta lontano dal reale.',
}

export function fmtNum(v: number | null | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(d)
}

export function strategyByKey(
  pattern: V31PatternAnalysis | null,
  key: string,
): V31PatternStrategyBlock | undefined {
  return pattern?.strategies.find((s) => s.key === key)
}

export function simStrategyByKey(
  sim: V31CalibrationSimulator | null,
  key: string,
): V31CalibrationSimulatorStrategy | undefined {
  return sim?.strategies.find((s) => s.key === key)
}

export function labelFor(sim: V31CalibrationSimulator | null, key?: string | null): string {
  if (!key) return '—'
  return sim?.strategies.find((s) => s.key === key)?.label ?? key
}

export function deriveMainIssue(pattern: V31PatternAnalysis | null): string {
  const rec = pattern?.summary.recommendations?.find((r) => r.type === 'structural')
  if (rec?.message) return rec.message
  const bias = strategyByKey(pattern, 'v31_bias_corrected')
  const hne = bias?.high_total_non_extreme_summary as
    | { understated_pct?: number; count_high_non_extreme?: number }
    | undefined
  if ((hne?.understated_pct ?? 0) >= 40) {
    return 'Tutti i modelli sottostimano le high non estreme.'
  }
  return 'Modelli ancora troppo piatti sulle partite alte non estreme.'
}

export function predictedHighCount(block: V31PatternStrategyBlock | undefined): number {
  const h = block?.high_and_outlier as Record<string, unknown> | undefined
  if (!h) return 0
  return Number(h.predicted_high ?? 0) + Number(h.predicted_very_high ?? 0)
}

export function auditOk(pattern: V31PatternAnalysis | null): boolean {
  const audit = pattern?.audit
  if (!audit) return false
  return Object.values(audit).every((v) => v === true)
}

export function clusterExamples(
  fixtures: V31Top3FixtureComparison[],
  cluster: string,
  limit = 3,
): V31Top3FixtureComparison[] {
  return fixtures.filter((f) => f.top3_cluster === cluster).slice(0, limit)
}

export function filterFixturesByWinQuality(
  fixtures: V31Top3FixtureComparison[],
  modelKey: string,
  quality: V31WinQuality | 'all',
): V31Top3FixtureComparison[] {
  if (quality === 'all') return fixtures
  return fixtures.filter((f) => f.models?.[modelKey]?.win_quality === quality)
}

export const NEXT_MODEL_DIRECTION =
  'La base più solida resta v31_bias_corrected. La nuova direzione è costruire un candidato ibrido che usi la stabilità del bias corrected, recuperi alcuni segnali utili da chaos_game, ma introduca guardrail più severi per evitare false high prediction.'
