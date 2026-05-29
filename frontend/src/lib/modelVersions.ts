/** Versioni modello visibili in UI principale (ordine display). */
export const UI_MODEL_VERSION_SLUGS = [
  'baseline_v2_1_weighted_components',
  'baseline_v2_0_lineup_impact',
] as const

export type UiModelVersionSlug = (typeof UI_MODEL_VERSION_SLUGS)[number]

export const LEGACY_MODEL_VERSIONS = new Set<string>([
  'baseline_v0_1',
  'baseline_v0_2_context_player',
  'baseline_v0_2_player_adjusted',
  'baseline_v0_3_core_sot',
  'baseline_v1_0_sot',
  'baseline_v1_1_sot',
  'baseline_v0_4_offensive_core_sot',
])

export const MODEL_VERSION_LABELS: Record<string, string> = {
  baseline_v2_1_weighted_components: 'v2.1 SOT Weighted Components',
  baseline_v2_0_lineup_impact: 'v2.0 SOT Lineup Impact',
  baseline_v1_1_sot: 'v1.1 SOT',
}

export const MODEL_STAGE_BADGES: Record<string, string> = {
  baseline_v2_1_weighted_components: 'Weighted Components',
  baseline_v2_0_lineup_impact: 'Lineup Impact',
  baseline_v1_1_sot: 'stabile',
}

export const MODEL_STAGE_DESCRIPTIONS: Record<string, string> = {
  baseline_v2_1_weighted_components:
    'Modello sperimentale con 10 macroaree e micro-variabili pesate (schema PDF). Engine autonomo v2.1 attivo.',
  baseline_v2_0_lineup_impact:
    'Impatto formazioni, indisponibili, sostituti e filtro rosa attuale su base v1.1.',
  baseline_v1_1_sot:
    'Produzione offensiva, difensiva, split casa/trasferta, forma recente, xG e player layer (6 termini).',
}

export const V21_MODEL = 'baseline_v2_1_weighted_components' as const
export const V21_ENGINE_NOT_READY = 'experimental_not_ready' as const
export const V21_ENGINE_READY = 'ready' as const
export const V21_MANIFEST_INVALID = 'manifest_invalid' as const
export const V20_MODEL = 'baseline_v2_0_lineup_impact' as const
export const V11_MODEL = 'baseline_v1_1_sot' as const
/** Solo azioni admin legacy — non in dropdown UI principale */
export const V10_MODEL = 'baseline_v1_0_sot' as const
export const V04_MODEL = 'baseline_v0_4_offensive_core_sot' as const

export type OperatingMode = 'complete' | 'degraded_fallback' | 'not_ready'

export function labelForOperatingMode(mode: string | undefined | null): string {
  if (mode === 'complete') return 'Completa'
  if (mode === 'degraded_fallback') return 'Fallback (senza lineups)'
  if (mode === 'not_ready') return 'Non pronto'
  return '—'
}

export function formatInputsAvailable(inputs?: Record<string, boolean> | null): string {
  if (!inputs) return '—'
  const parts: string[] = []
  if (inputs.team_stats) parts.push('team stats')
  if (inputs.player_profiles) parts.push('profili giocatori')
  if (inputs.lineups) parts.push('lineups SportAPI')
  if (inputs.sportapi_mappings) parts.push('mapping SportAPI')
  if (inputs.v11_base_ready) parts.push('base v1.1')
  return parts.length ? parts.join(', ') : 'nessuno'
}

export function formatModelStatusFootnote(ctx?: {
  lineups_probable_only?: boolean
  next_round_lineup_coverage_pct?: number
  lineups_ready?: boolean
  operating_mode?: string
} | null): string | null {
  if (!ctx) return null
  if (ctx.lineups_probable_only) {
    return 'Formazioni probabili, non ufficiali.'
  }
  const cov = ctx.next_round_lineup_coverage_pct
  if (ctx.lineups_ready && cov != null && cov >= 100) {
    return 'Formazioni SportAPI disponibili per tutto il prossimo turno.'
  }
  if (ctx.operating_mode === 'degraded_fallback' || ctx.lineups_ready === false) {
    return 'Lineups mancanti.'
  }
  return null
}

export function labelForModelVersion(slug: string): string {
  return MODEL_VERSION_LABELS[slug] ?? slug
}

export function stageBadgeForModel(slug: string): string {
  return MODEL_STAGE_BADGES[slug] ?? '—'
}

export function stageDescriptionForModel(slug: string): string {
  return MODEL_STAGE_DESCRIPTIONS[slug] ?? ''
}

export function isUiModelVersion(slug: string): boolean {
  return (UI_MODEL_VERSION_SLUGS as readonly string[]).includes(slug)
}

export function filterVersionsForUi<T extends { model_version: string }>(rows: T[]): T[] {
  return rows.filter((r) => isUiModelVersion(r.model_version))
}

export function isV21EngineNotReadyRow(row: {
  model_version?: string
  engine_status?: string
}): boolean {
  return row.model_version === V21_MODEL && row.engine_status === V21_ENGINE_NOT_READY
}

export function isV21ExperimentalRow(row: {
  model_version?: string
  engine_status?: string
  is_experimental?: boolean
}): boolean {
  return (
    row.model_version === V21_MODEL ||
    row.engine_status === V21_ENGINE_NOT_READY ||
    row.engine_status === V21_MANIFEST_INVALID ||
    row.is_experimental === true
  )
}

export function isV21ManifestInvalidRow(row: {
  model_version?: string
  engine_status?: string
}): boolean {
  return row.model_version === V21_MODEL && row.engine_status === V21_MANIFEST_INVALID
}

export function resolveDisplayedModelFromStatus(
  status: {
    selected_model_version?: string | null
    selected_model_label?: string | null
    recommended_model_version?: string | null
    recommended_model_label?: string | null
    active_model_version?: string | null
  } | null | undefined,
  selectedModelVersion: string,
): { version: string; label: string } {
  const version =
    status?.selected_model_version ??
    status?.active_model_version ??
    status?.recommended_model_version ??
    selectedModelVersion
  const label =
    (status?.selected_model_version === version ? status?.selected_model_label : null) ??
    (status?.recommended_model_version === version ? status?.recommended_model_label : null) ??
    labelForModelVersion(version)
  return { version, label }
}

export const MODEL_OPTIONS_AUDIT: { value: string; label: string }[] = [
  { value: V21_MODEL, label: MODEL_VERSION_LABELS[V21_MODEL] },
  { value: V20_MODEL, label: MODEL_VERSION_LABELS[V20_MODEL] },
]
