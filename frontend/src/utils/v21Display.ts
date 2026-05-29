export type WeightScale = 'fraction' | 'manifest_points'

export function roundAuditNumber(v: number): number {
  return Math.round(v * 100) / 100
}

export function formatAuditNumber(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'string' && Number.isNaN(Number(v))) return v
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  const rounded = roundAuditNumber(n)
  if (Number.isInteger(rounded)) return String(rounded)
  return rounded.toFixed(2)
}

/** Peso manifest v2.1: 16 → 16%. Peso frazione v11: 0.16 → 16%. */
export function formatV21ManifestWeight(
  w: number | null | undefined,
  scale: WeightScale = 'manifest_points',
): string {
  if (w == null || !Number.isFinite(Number(w))) return '—'
  const n = Number(w)
  if (scale === 'manifest_points' || n > 1) {
    const pct = scale === 'manifest_points' ? n : n * 100
    const rounded = roundAuditNumber(pct)
    if (Number.isInteger(rounded)) return `${rounded}%`
    return `${rounded.toFixed(2)}%`
  }
  const pct = roundAuditNumber(n * 100)
  if (Number.isInteger(pct)) return `${pct}%`
  return `${pct.toFixed(2)}%`
}

export function formatTraceWeight(
  w: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (w == null) return '—'
  if (unit === 'peso macro' || unit === 'peso micro') {
    return formatV21ManifestWeight(w, 'manifest_points')
  }
  return formatAuditNumber(w)
}
