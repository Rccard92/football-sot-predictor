import type { RoundAnalysisModelBlock } from './api'

export type V30HumanExplanation = {
  headline?: string
  summary?: string
  decision_reason?: string
  risk_reason?: string
  line_reason?: string
  confidence_reason?: string
  key_factors?: string[]
  warning_notes?: string[]
  italian_text?: string
  short_reason?: string
  data_used?: Record<string, number | string | null | undefined>
}

const NO_BET_SHORT_IT: Record<string, string> = {
  V11_PRED_TOO_LOW_FOR_7_5: 'v1.1 non conferma 7.5',
  V21_PRED_TOO_LOW_FOR_7_5: '7.5 non premium',
  MACRO_OVERHEAT: 'Macro troppo spinte',
  V21_V11_GAP_TOO_HIGH: 'Gap v2.1–v1.1 alto',
  TOO_MANY_WARNINGS: 'Troppi warning',
  LINE_5_5_EXCLUDED: 'Linea 5.5 esclusa',
  CONFIDENCE_LOW: 'Confidence bassa',
  INJURIES_LOW: 'Indisponibili penalizzanti',
  LINEUP_WEAK: 'Formazioni deboli',
  INJURY_PLAYER_LAYER_WEAK: 'Assenze + player layer',
}

function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  const n = Number(v)
  return n.toFixed(decimals).replace(/\.?0+$/, '')
}

export function getV30HumanExplanation(
  block: RoundAnalysisModelBlock | undefined,
): V30HumanExplanation | null {
  if (!block) return null
  const root = block.human_explanation as V30HumanExplanation | undefined
  if (root && typeof root === 'object') return root
  const ts = block.trace_summary as { human_explanation?: V30HumanExplanation } | undefined
  const fromTrace = ts?.human_explanation
  if (fromTrace && typeof fromTrace === 'object') return fromTrace
  return null
}

export function getV30ReferenceTotals(
  block: RoundAnalysisModelBlock | undefined,
  explanationSlice?: Record<string, unknown> | null,
): { v11: number | null; v21: number | null; gap: number | null } {
  if (!block) return { v11: null, v21: null, gap: null }

  const ts = block.trace_summary as Record<string, unknown> | undefined
  let v11 =
    (block as { v1_1_predicted_total?: number }).v1_1_predicted_total ??
    (ts?.v1_1_predicted_total as number | undefined) ??
    null
  let v21 =
    (block as { v2_1_predicted_total?: number }).v2_1_predicted_total ??
    (ts?.v2_1_predicted_total as number | undefined) ??
    null

  if (explanationSlice) {
    const ref11 = explanationSlice.reference_v1_1 as { predicted_total_sot?: number } | undefined
    const ref21 = explanationSlice.reference_v2_1 as { predicted_total_sot?: number } | undefined
    if (v11 == null && ref11?.predicted_total_sot != null) v11 = Number(ref11.predicted_total_sot)
    if (v21 == null && ref21?.predicted_total_sot != null) v21 = Number(ref21.predicted_total_sot)
  }

  let gap =
    (block as { prediction_gap?: number }).prediction_gap ??
    (ts?.prediction_gap as number | undefined) ??
    null
  if (gap == null && v11 != null && v21 != null) {
    gap = Math.round((v21 - v11) * 100) / 100
  }

  return { v11, v21, gap }
}

export function formatV30TotalsDisplay(
  block: RoundAnalysisModelBlock | undefined,
  explanationSlice?: Record<string, unknown> | null,
): string {
  const { v11, v21, gap } = getV30ReferenceTotals(block, explanationSlice)
  if (v11 == null && v21 == null) return '— / —'
  const gapStr =
    gap != null ? ` (gap ${gap >= 0 ? '+' : ''}${fmtNum(gap)})` : ''
  return `${fmtNum(v11)} / ${fmtNum(v21)}${gapStr}`
}

export function v30TableShortReason(
  block: RoundAnalysisModelBlock | undefined,
): { display: string; title: string } {
  const human = getV30HumanExplanation(block)
  if (human?.short_reason) {
    return {
      display: human.short_reason,
      title: human.italian_text || human.summary || human.short_reason,
    }
  }

  const ts = block?.trace_summary as {
    selection?: { reason_codes?: string[]; no_bet_reasons?: string[] }
  } | undefined
  const sel = ts?.selection ?? {}
  const codes = [...(sel.reason_codes ?? []), ...(sel.no_bet_reasons ?? [])]
  const primary = codes[0] ?? ''
  const display = NO_BET_SHORT_IT[primary] || (primary ? primary.replace(/_/g, ' ').toLowerCase() : '')
  return { display, title: codes.join(', ') }
}
