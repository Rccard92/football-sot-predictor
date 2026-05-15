/** Versioni modello visibili in UI principale (ordine display). */
export const UI_MODEL_VERSION_SLUGS = [
  'baseline_v1_1_sot',
  'baseline_v1_0_sot',
  'baseline_v0_4_offensive_core_sot',
] as const

export type UiModelVersionSlug = (typeof UI_MODEL_VERSION_SLUGS)[number]

export const LEGACY_MODEL_VERSIONS = new Set<string>([
  'baseline_v0_1',
  'baseline_v0_2_context_player',
  'baseline_v0_2_player_adjusted',
  'baseline_v0_3_core_sot',
])

export const MODEL_VERSION_LABELS: Record<string, string> = {
  baseline_v1_1_sot: 'v1.1 SOT (produzione offensiva)',
  baseline_v1_0_sot: 'v1.0 SOT (xG)',
  baseline_v0_4_offensive_core_sot: 'v0.4 offensive core',
}

export const V11_MODEL = 'baseline_v1_1_sot' as const
export const V10_MODEL = 'baseline_v1_0_sot' as const
export const V04_MODEL = 'baseline_v0_4_offensive_core_sot' as const

export function labelForModelVersion(slug: string): string {
  return MODEL_VERSION_LABELS[slug] ?? slug
}

export function isUiModelVersion(slug: string): boolean {
  return (UI_MODEL_VERSION_SLUGS as readonly string[]).includes(slug)
}

export function filterVersionsForUi<T extends { model_version: string }>(rows: T[]): T[] {
  return rows.filter((r) => isUiModelVersion(r.model_version))
}

export const MODEL_OPTIONS_AUDIT: { value: string; label: string }[] = [
  { value: '', label: 'Automatico (consigliato dal server)' },
  { value: V11_MODEL, label: MODEL_VERSION_LABELS[V11_MODEL] },
  { value: V10_MODEL, label: MODEL_VERSION_LABELS[V10_MODEL] },
  { value: V04_MODEL, label: MODEL_VERSION_LABELS[V04_MODEL] },
]
