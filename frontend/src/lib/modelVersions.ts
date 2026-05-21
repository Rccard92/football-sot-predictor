/** Versioni modello visibili in UI principale (ordine display). */
export const UI_MODEL_VERSION_SLUGS = [
  'baseline_v2_0_lineup_impact',
  'baseline_v1_1_sot',
] as const

export type UiModelVersionSlug = (typeof UI_MODEL_VERSION_SLUGS)[number]

export const LEGACY_MODEL_VERSIONS = new Set<string>([
  'baseline_v0_1',
  'baseline_v0_2_context_player',
  'baseline_v0_2_player_adjusted',
  'baseline_v0_3_core_sot',
  'baseline_v1_0_sot',
  'baseline_v0_4_offensive_core_sot',
])

export const MODEL_VERSION_LABELS: Record<string, string> = {
  baseline_v2_0_lineup_impact: 'v2.0 SOT Lineup Impact',
  baseline_v1_1_sot: 'v1.1 SOT',
}

export const MODEL_STAGE_BADGES: Record<string, string> = {
  baseline_v2_0_lineup_impact: 'Lineup Impact',
  baseline_v1_1_sot: 'stabile',
}

export const MODEL_STAGE_DESCRIPTIONS: Record<string, string> = {
  baseline_v2_0_lineup_impact:
    'Impatto formazioni, indisponibili, sostituti e filtro rosa attuale su base v1.1.',
  baseline_v1_1_sot:
    'Produzione offensiva, difensiva, split casa/trasferta, forma recente, xG e player layer (6 termini).',
}

export const V20_MODEL = 'baseline_v2_0_lineup_impact' as const
export const V11_MODEL = 'baseline_v1_1_sot' as const
/** Solo azioni admin legacy — non in dropdown UI principale */
export const V10_MODEL = 'baseline_v1_0_sot' as const
export const V04_MODEL = 'baseline_v0_4_offensive_core_sot' as const

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

export const MODEL_OPTIONS_AUDIT: { value: string; label: string }[] = [
  { value: '', label: 'Automatico (consigliato dal server)' },
  { value: V20_MODEL, label: MODEL_VERSION_LABELS[V20_MODEL] },
  { value: V11_MODEL, label: MODEL_VERSION_LABELS[V11_MODEL] },
]
