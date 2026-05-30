import type { FormulaComponentTableRow, PredictionFormulaBreakdownSide } from '../types/sotExplanation'
import { formatAuditNumber, formatV21ManifestWeight, roundAuditNumber } from './v21Display'

export const ANCHOR_TEAM_SOT_WEIGHT = 0.55
export const ANCHOR_OPP_SOT_CONCEDED_WEIGHT = 0.45

export const MACRO_EFFECT_PUSH_UP_THRESHOLD = 1.03
export const MACRO_EFFECT_PUSH_DOWN_THRESHOLD = 0.97

export type MacroEffectKind = 'push_up' | 'neutral' | 'push_down'

export type V21FormulaValues = {
  baseAnchor: number | null
  macroMultiplier: number | null
  finalSot: number | null
  teamSotAvg: number | null
  oppSotConcededAvg: number | null
  anchorFormulaExpr: string | null
}

export const V21_MACRO_DERIVED_FROM: Record<string, string> = {
  offensive_production:
    'Combina tiri in porta, tiri totali, precisione tiro, tiri in area, tiri bloccati, gol e trend offensivo.',
  opponent_defensive_resistance:
    'Misura quanto l’avversario concede: SOT subiti, tiri totali concessi, tiri in area concessi e trend difensivo.',
  home_away_split:
    'Confronta il rendimento della squadra e dell’avversario nel contesto casa/trasferta.',
  recent_form:
    'Guarda il rendimento più recente rispetto alla media stagionale.',
  chance_quality:
    'Usa gli xG reali: xG prodotti, xG concessi dall’avversario e delta rispetto alla media lega.',
  player_layer:
    'Analizza il peso dei giocatori offensivi principali, la loro produzione SOT e la loro presenza nella formazione.',
  lineups:
    'Valuta se la formazione è probabile o ufficiale, chi parte titolare e il peso offensivo dell’undici iniziale.',
  injuries_unavailable:
    'Valuta assenze, squalifiche, top shooter assenti e peso dei giocatori indisponibili.',
  pace_control:
    'Analizza possesso, passaggi, precisione e ritmo stimato della squadra.',
}

function termValue(formula: PredictionFormulaBreakdownSide, symbol: string): number | null {
  const t = formula.terms?.find((x) => x.symbol === symbol)
  if (t?.value == null) return null
  const n = Number(t.value)
  return Number.isFinite(n) ? n : null
}

function anchorRow(
  table: FormulaComponentTableRow[] | undefined,
  componente: string,
): FormulaComponentTableRow | undefined {
  return table?.find((r) => r.componente === componente)
}

export function extractV21FormulaValues(formula: PredictionFormulaBreakdownSide): V21FormulaValues {
  const anchorTable = formula.anchor_breakdown_table
  const baseFromTerm = termValue(formula, 'base_anchor_sot')
  const baseFromTable = anchorRow(anchorTable, 'Base anchor SOT')?.valore_componente
  const multFromTerm = termValue(formula, 'weighted_macro_multiplier')
  const multFromTable = formula.components_table?.find((r) => r.componente === 'Moltiplicatore macro')?.valore_componente
  const finalFromTerm = termValue(formula, 'expected_sot_v21')
  const finalFromStored = formula.stored_predicted_sot

  const teamRow = anchorRow(anchorTable, 'Media SOT fatti squadra')
  const oppRow = anchorRow(anchorTable, 'Media SOT concessi avversario')
  const baseRow = anchorRow(anchorTable, 'Base anchor SOT')

  return {
    baseAnchor: baseFromTerm ?? (baseFromTable != null ? Number(baseFromTable) : null),
    macroMultiplier: multFromTerm ?? (multFromTable != null ? Number(multFromTable) : null),
    finalSot: finalFromTerm ?? (finalFromStored != null ? Number(finalFromStored) : null),
    teamSotAvg: teamRow?.valore_componente != null ? Number(teamRow.valore_componente) : null,
    oppSotConcededAvg: oppRow?.valore_componente != null ? Number(oppRow.valore_componente) : null,
    anchorFormulaExpr: baseRow?.calcolo_contributo ?? null,
  }
}

export function getMacroEffect(index: number): MacroEffectKind {
  if (index > MACRO_EFFECT_PUSH_UP_THRESHOLD) return 'push_up'
  if (index < MACRO_EFFECT_PUSH_DOWN_THRESHOLD) return 'push_down'
  return 'neutral'
}

export function macroEffectLabel(kind: MacroEffectKind): string {
  if (kind === 'push_up') return 'Spinge su'
  if (kind === 'push_down') return 'Frena'
  return 'Neutra'
}

export function formatMultiplierPctChange(multiplier: number | null): string | null {
  if (multiplier == null || !Number.isFinite(multiplier)) return null
  const pct = roundAuditNumber((multiplier - 1) * 100)
  if (Math.abs(pct) < 0.05) return '0%'
  const sign = pct > 0 ? '+' : ''
  if (Number.isInteger(pct)) return `${sign}${pct}%`
  return `${sign}${pct.toFixed(1)}%`
}

export function macroMultiplierTrendText(multiplier: number | null): string {
  if (multiplier == null || !Number.isFinite(multiplier)) return 'Le macroaree influenzano la previsione base.'
  if (multiplier > 1.03) return 'Le macroaree aumentano la previsione.'
  if (multiplier < 0.97) return 'Le macroaree riducono la previsione.'
  return 'Le macroaree lasciano la previsione quasi stabile.'
}

export type MacroHighlight = {
  componente: string
  macroKey: string | null
  index: number
  weightPct: string
  effect: MacroEffectKind
}

export function pickMacroHighlight(rows: FormulaComponentTableRow[] | undefined): MacroHighlight | null {
  if (!rows?.length) return null
  let best: MacroHighlight | null = null
  let bestDistance = -1

  for (const row of rows) {
    const index = row.valore_componente != null ? Number(row.valore_componente) : null
    if (index == null || !Number.isFinite(index)) continue
    const distance = Math.abs(index - 1)
    if (distance <= bestDistance) continue
    bestDistance = distance
    best = {
      componente: row.componente,
      macroKey: row.macro_key ?? null,
      index,
      weightPct: formatV21ManifestWeight(row.peso, 'manifest_points'),
      effect: getMacroEffect(index),
    }
  }
  return best
}

export function macroHighlightSentence(highlight: MacroHighlight | null): string | null {
  if (!highlight) return null
  const idx = formatAuditNumber(highlight.index)
  const direction =
    highlight.effect === 'push_up'
      ? 'spinge la previsione verso l’alto'
      : highlight.effect === 'push_down'
        ? 'spinge la previsione verso il basso'
        : 'resta quasi neutra'
  const importance = highlight.effect === 'neutral' ? '' : ' in modo importante'
  return `${highlight.componente} ha indice ${idx} e peso ${highlight.weightPct}, quindi ${direction}${importance}.`
}

export function formatSotValue(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return formatAuditNumber(value)
}
