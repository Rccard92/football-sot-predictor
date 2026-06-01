import type { RoundAnalysisModelBlock } from '../../lib/api'

export function hitRateBadgeClass(hitRate: number | null | undefined): string {
  if (hitRate == null) return 'bg-slate-100 text-slate-600'
  if (hitRate >= 70) return 'bg-emerald-100 text-emerald-800'
  if (hitRate >= 55) return 'bg-amber-100 text-amber-900'
  return 'bg-rose-100 text-rose-800'
}

export function dataQualityBadgeClass(badge: string | null | undefined): string {
  if (badge === 'OK') return 'bg-emerald-100 text-emerald-800'
  if (badge === 'Avvisi') return 'bg-amber-100 text-amber-900'
  if (badge === 'Critico') return 'bg-rose-100 text-rose-800'
  return 'bg-slate-100 text-slate-600'
}

export function modelDisplayBadgeClass(display: string | undefined): string {
  if (display === 'OK') return 'bg-emerald-100 text-emerald-800'
  if (display === 'WARNINGS') return 'bg-amber-100 text-amber-900'
  if (display === 'ERROR') return 'bg-rose-100 text-rose-800'
  return 'bg-slate-100 text-slate-600'
}

export function ndBadgeClass(): string {
  return 'bg-slate-100 text-slate-600'
}

export type PickCellDisplay = {
  label: string
  sublabel?: string
  isNd: boolean
  title?: string
}

/** Etichette leggibili per error_code Round Analysis. */
export const ERROR_CODE_LABELS_IT: Record<string, string> = {
  V11_PREDICTION_INCOMPLETE: 'Output v1.1 incompleto',
  V11_MISSING_TOTAL_SOT: 'Predizione totale mancante',
  V11_PRIOR_CONTEXT_EMPTY: 'Storico non recuperato',
  V11_INSUFFICIENT_PRIOR_MATCHES: 'Prior insufficienti v1.1',
  V11_INSUFFICIENT_GENERAL_SAMPLE: 'Campione generale insufficiente',
  V11_INSUFFICIENT_SPLIT_SAMPLE: 'Campione split casa/trasferta insufficiente',
  V11_SPLIT_SAMPLE_INSUFFICIENT_USED_GENERAL_BASE: 'Split insufficiente → base generale',
  V11_LEAGUE_BASELINE_EMPTY: 'Baseline lega vuota',
  V11_MISSING_XG_LEAGUE_BASELINE: 'Baseline xG lega mancante',
  V11_MISSING_PLAYER_LEAGUE_BASELINE: 'Baseline player lega mancante',
  V11_MISSING_LEAGUE_SPLIT_BASELINE: 'Baseline split lega mancante',
  V11_MISSING_RECENT_LEAGUE_BASELINE: 'Baseline recent lega mancante',
  V11_INSUFFICIENT_PLAYER_PROFILE: 'Profilo player insufficiente',
  V11_INSUFFICIENT_SAMPLE: 'Campione insufficiente v1.1',
  V11_INSUFFICIENT_RECENT_SAMPLE: 'Campione recent insufficiente',
  V11_INSUFFICIENT_XG_SAMPLE: 'Campione xG insufficiente',
  V11_OUTPUT_MAPPING_FAILED: 'Mapping output v1.1 fallito',
  V11_MISSING_TEAM_STATS: 'Team stats mancanti',
  V11_ENGINE_ERROR: 'Errore motore v1.1',
  V20_V11_BASE_FAILED: 'Base v1.1 non disponibile',
  V20_REQUIRES_HOME_AWAY_BASE: 'Richiesti home/away base v1.1',
  V20_LINEUP_DATA_MISSING: 'Lineup mancante v2.0',
  V20_PLAYER_LAYER_MISSING: 'Player layer mancante',
  V20_INSUFFICIENT_PRIOR_MATCHES: 'Prior insufficienti v2.0',
  V20_PREDICTION_INCOMPLETE: 'Output v2.0 incompleto',
  V20_ENGINE_ERROR: 'Errore motore v2.0',
  V21_INSUFFICIENT_PRIOR_MATCHES: 'Prior insufficienti v2.1',
  V21_PREDICTION_INCOMPLETE: 'Preview v2.1 incompleta',
  V21_ENGINE_ERROR: 'Errore motore v2.1',
  MODEL_VERSION_MISMATCH: 'Versione modello non corrispondente',
  MODEL_ERROR: 'Errore generico modello',
  INSUFFICIENT_HISTORY: 'Storico insufficiente',
}

export function errorCodeLabelIt(code: string | null | undefined): string {
  if (!code) return 'N/D'
  return ERROR_CODE_LABELS_IT[code] ?? code
}

function ndSublabel(block: RoundAnalysisModelBlock): { sublabel: string; title?: string } {
  const code = block.error_code || block.reason
  if (code && code !== 'INSUFFICIENT_HISTORY') {
    const label = errorCodeLabelIt(code)
    return {
      sublabel: label.length > 24 ? `${label.slice(0, 24)}…` : label,
      title: block.error_message || block.message || code,
    }
  }
  if (block.reason === 'INSUFFICIENT_HISTORY' || block.error_code === 'V11_INSUFFICIENT_PRIOR_MATCHES') {
    return { sublabel: 'Storico insuff.', title: block.error_message || block.message || undefined }
  }
  return {
    sublabel: block.error_code || block.message?.slice(0, 40) || 'N/D',
    title: block.error_message || block.message || undefined,
  }
}

export function pickCell(
  block: RoundAnalysisModelBlock | undefined,
  kind: 'aggressive' | 'cautious',
): PickCellDisplay {
  if (!block) {
    return { label: 'ND', sublabel: 'N/D', isNd: true }
  }
  if (block.status === 'error') {
    const { sublabel, title } = ndSublabel(block)
    return { label: 'ERR', sublabel, isNd: true, title }
  }
  if (block.status === 'no_prediction') {
    const { sublabel, title } = ndSublabel(block)
    return { label: 'ND', sublabel, isNd: true, title }
  }

  const line = kind === 'aggressive' ? block.aggressive_line : block.cautious_line
  const outcome = kind === 'aggressive' ? block.aggressive_outcome : block.cautious_outcome
  const advice = kind === 'aggressive' ? block.aggressive_advice : block.cautious_advice

  if (line == null && block.predicted_total_sot == null) {
    const { sublabel, title } = ndSublabel(block)
    return { label: 'ND', sublabel, isNd: true, title }
  }
  if (line == null) {
    return { label: advice || 'ND', sublabel: undefined, isNd: !advice }
  }
  return { label: `${line} · ${outcome ?? '—'}`, sublabel: undefined, isNd: false }
}

export const MODEL_KEYS = {
  v11: 'baseline_v1_1_sot',
  v20: 'baseline_v2_0_lineup_impact',
  v21: 'baseline_v2_1_weighted_components',
} as const

export function seasonLabelFromYear(year: number): string {
  return `${year}/${year + 1}`
}

export function statusLabelIt(status: string | undefined): string {
  switch (status) {
    case 'completed':
      return 'Completata'
    case 'completed_with_warnings':
      return 'Completata con avvisi'
    case 'failed':
      return 'Fallita'
    default:
      return status ?? '—'
  }
}
