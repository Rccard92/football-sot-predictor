/**
 * Download JSON generico + helper export analisi statistica Credibilità X.
 * Il payload completo non viene trasformato: solo JSON.stringify(data, null, 2).
 */

export type StatisticsExportSectionKey =
  | 'dataset_summary'
  | 'research_maturity'
  | 'feature_leaderboard'
  | 'numeric_feature_analysis'
  | 'categorical_feature_analysis'
  | 'probability_calibration'
  | 'redundancy_analysis'
  | 'primary_vs_sensitivity'
  | 'interaction_analysis'
  | 'candidate_patterns'
  | 'pattern_consistency_checks'
  | 'temporal_stability'
  | 'league_stability'
  | 'market_analysis'
  | 'research_conclusions'
  | 'performance'
  | 'warnings'

export const STATISTICS_EXPORT_SECTIONS: Array<{
  key: StatisticsExportSectionKey
  label: string
}> = [
  { key: 'dataset_summary', label: 'Dataset summary' },
  { key: 'research_maturity', label: 'Research maturity' },
  { key: 'feature_leaderboard', label: 'Feature leaderboard' },
  { key: 'numeric_feature_analysis', label: 'Numeric feature analysis' },
  { key: 'categorical_feature_analysis', label: 'Categorical feature analysis' },
  { key: 'probability_calibration', label: 'Probability calibration' },
  { key: 'redundancy_analysis', label: 'Redundancy analysis' },
  { key: 'primary_vs_sensitivity', label: 'Primary vs Sensitivity' },
  { key: 'interaction_analysis', label: 'Interaction analysis' },
  { key: 'candidate_patterns', label: 'Candidate patterns' },
  { key: 'pattern_consistency_checks', label: 'Pattern consistency checks' },
  { key: 'temporal_stability', label: 'Temporal stability' },
  { key: 'league_stability', label: 'League stability' },
  { key: 'market_analysis', label: 'Market analysis' },
  { key: 'research_conclusions', label: 'Research conclusions' },
  { key: 'performance', label: 'Performance' },
  { key: 'warnings', label: 'Warnings' },
]

export function sanitizeFilenameFragment(value: string): string {
  return String(value ?? '')
    .trim()
    .replace(/[^\w.-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 120) || 'unknown'
}

export function buildStatisticsFullFilename(
  version: string,
  dateFrom: string,
  dateTo: string,
): string {
  const v = sanitizeFilenameFragment(version)
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  // Evita doppio prefisso se version è già lo slug completo (es. …_statistics_v1_2)
  const stem = v.startsWith('cecchino_draw_credibility_statistics')
    ? v
    : `cecchino_draw_credibility_statistics_${v}`
  return `${stem}_${from}_${to}.json`
}

export function buildStatisticsSectionFilename(
  section: string,
  dateFrom: string,
  dateTo: string,
): string {
  const s = sanitizeFilenameFragment(section)
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  return `cecchino_draw_credibility_${s}_${from}_${to}.json`
}

export type StatisticsSectionExportPayload = {
  status: string
  version: string
  filters: unknown
  exported_section: string
  exported_at: string
  data: unknown
}

/** Wrapper sezione: `data` è il riferimento originale alla sezione, non una copia trasformata. */
export function buildStatisticsSectionExport(
  response: {
    status: string
    version: string
    filters: unknown
    [key: string]: unknown
  },
  sectionKey: StatisticsExportSectionKey,
  exportedAt: string = new Date().toISOString(),
): StatisticsSectionExportPayload {
  return {
    status: response.status,
    version: response.version,
    filters: response.filters,
    exported_section: sectionKey,
    exported_at: exportedAt,
    data: response[sectionKey],
  }
}

export function estimateJsonByteSize(data: unknown): number {
  const text = JSON.stringify(data, null, 2)
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(text).length
  }
  return text.length
}

export function formatApproxJsonSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1024) return `~${bytes} B`
  if (bytes < 1024 * 1024) return `~${(bytes / 1024).toFixed(1)} KB`
  return `~${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

/**
 * Serializza e scarica un file JSON.
 * @throws Error se JSON.stringify fallisce (es. riferimento ciclico)
 */
export function downloadJsonFile(filename: string, data: unknown): void {
  let text: string
  try {
    text = JSON.stringify(data, null, 2)
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    throw new Error(`Serializzazione JSON non riuscita: ${message}`, { cause: err })
  }
  if (text === undefined) {
    throw new Error('Serializzazione JSON non riuscita: risultato undefined')
  }
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function downloadTextFile(
  filename: string,
  text: string,
  mime: string = 'text/plain;charset=utf-8',
): void {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function csvEscapeCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  const s = String(value)
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

export function buildCsvContent(headers: string[], rows: Array<Array<unknown>>): string {
  const lines = [headers.map(csvEscapeCell).join(',')]
  for (const row of rows) {
    lines.push(row.map(csvEscapeCell).join(','))
  }
  return lines.join('\n')
}

export function downloadCsvFile(filename: string, headers: string[], rows: Array<Array<unknown>>): void {
  downloadTextFile(filename, buildCsvContent(headers, rows), 'text/csv;charset=utf-8')
}

export function buildModelComparisonFullFilename(dateFrom: string, dateTo: string): string {
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  return `cecchino_draw_credibility_model_comparison_${from}_${to}.json`
}

export function buildModelComparisonOofCsvFilename(dateFrom: string, dateTo: string): string {
  const from = sanitizeFilenameFragment(dateFrom)
  const to = sanitizeFilenameFragment(dateTo)
  return `cecchino_draw_credibility_model_comparison_oof_${from}_${to}.csv`
}
