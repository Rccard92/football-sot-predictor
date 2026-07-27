/** Token colore Overview betting — estensione del tema Lab. */

export const overviewColors = {
  home: '#2ee6ff',
  draw: '#f0b429',
  away: '#c084fc',
  over: '#3dd68c',
  under: '#5b8def',
  positive: '#3dd68c',
  negative: '#f07178',
  accent: '#2ee6ff',
  surface: 'rgba(21, 38, 58, 0.85)',
  border: 'rgba(120, 190, 220, 0.14)',
} as const

export function roiColor(roi: number | null | undefined): string {
  if (roi == null) return 'var(--lab-muted)'
  if (roi > 0) return overviewColors.positive
  if (roi < 0) return overviewColors.negative
  return 'var(--lab-muted)'
}

export function formatPct(v: number | null | undefined, digits = 1): string {
  if (v == null) return '—'
  return `${v.toFixed(digits)}%`
}

export function formatNum(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}

export function formatRoi(v: number | null | undefined): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}%`
}

/** Heatmap leggera 0–100 → rgba ciano. */
export function heatBg(pct: number | null | undefined, max = 100): string {
  if (pct == null) return 'transparent'
  const t = Math.max(0, Math.min(1, pct / max))
  return `rgba(46, 230, 255, ${0.04 + t * 0.22})`
}
