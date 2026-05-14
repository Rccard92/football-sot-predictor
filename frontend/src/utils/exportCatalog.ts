import type { ApiFootballDirectArea, ApiFootballDirectCatalogResponse, ApiFootballDirectField } from '../lib/api'

/** Data locale YYYY-MM-DD (nome file). */
export function formatCatalogExportDate(d = new Date()): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function sampleValueAsExportString(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

/** Riga canonica richiesta + tutti i campi originali del catalogo (nessuna perdita di informazione). */
export function buildExportParameter(
  field: ApiFootballDirectField,
  areaTitle: string,
  selectedIds: Set<string>,
): Record<string, unknown> {
  const isSelected = selectedIds.has(field.stable_id)
  const useful_markets: string[] = []
  const canonical = {
    key: field.stable_id,
    name_it: field.name_it,
    technical_name: field.technical_name,
    json_path: field.json_path,
    endpoint: field.endpoint,
    area: areaTitle,
    description_it: field.description_it,
    tooltip_it: field.tooltip_it ?? '',
    api_status: field.api_label || 'trovato_in_scan',
    db_status: field.db_status,
    model_v04_status: field.model_v04_status,
    implementation_status: '',
    useful_markets,
    difficulty: '',
    sample_value: sampleValueAsExportString(field.sample_value),
    sample_type: field.sample_type,
    is_selected: isSelected,
  }
  const raw = { ...field } as Record<string, unknown>
  return { ...raw, ...canonical }
}

export function countTotalFields(catalog: ApiFootballDirectCatalogResponse): number {
  return catalog.areas.reduce((acc, a) => acc + a.parameters.length, 0)
}

export function countSelectedInCatalog(catalog: ApiFootballDirectCatalogResponse, selectedIds: Set<string>): number {
  let n = 0
  for (const a of catalog.areas) {
    for (const p of a.parameters) {
      if (selectedIds.has(p.stable_id)) n++
    }
  }
  return n
}

export function buildFullCatalogExportPayload(
  catalog: ApiFootballDirectCatalogResponse,
  selectedIds: Set<string>,
): Record<string, unknown> {
  const total_fields = countTotalFields(catalog)
  const selected_fields = countSelectedInCatalog(catalog, selectedIds)
  const areas = catalog.areas.map((area) => buildExportArea(area, selectedIds))
  return {
    exported_at: new Date().toISOString(),
    catalog_version: catalog.version,
    provider: catalog.provider,
    season: catalog.season ?? null,
    last_scan_at: catalog.last_scan_at ?? null,
    message: catalog.message ?? null,
    summary: {
      ...catalog.summary,
      total_areas: catalog.areas.length,
      total_fields,
      selected_fields,
    },
    areas,
  }
}

function buildExportArea(area: ApiFootballDirectArea, selectedIds: Set<string>): Record<string, unknown> {
  const { parameters: _p, ...rest } = area
  return {
    ...rest,
    description: '',
    parameters: area.parameters.map((p) => buildExportParameter(p, area.title, selectedIds)),
  }
}

export function buildSelectedOnlyExportPayload(
  catalog: ApiFootballDirectCatalogResponse,
  selectedIds: Set<string>,
): Record<string, unknown> {
  const parameters: Record<string, unknown>[] = []
  for (const a of catalog.areas) {
    for (const p of a.parameters) {
      if (selectedIds.has(p.stable_id)) {
        parameters.push(buildExportParameter(p, a.title, selectedIds))
      }
    }
  }
  return {
    exported_at: new Date().toISOString(),
    catalog_version: catalog.version,
    provider: catalog.provider,
    season: catalog.season ?? null,
    last_scan_at: catalog.last_scan_at ?? null,
    message: catalog.message ?? null,
    count: parameters.length,
    parameters,
  }
}

export type CatalogCsvRow = {
  area_id: string
  area_title: string
  key: string
  name_it: string
  technical_name: string
  json_path: string
  endpoint: string
  description_it: string
  tooltip_it: string
  api_status: string
  db_status: string
  model_v04_status: string
  implementation_status: string
  useful_markets: string
  difficulty: string
  sample_value: string
  sample_type: string
  is_selected: string
}

export function flattenCatalogForCsv(
  catalog: ApiFootballDirectCatalogResponse,
  selectedIds: Set<string>,
): CatalogCsvRow[] {
  const rows: CatalogCsvRow[] = []
  for (const a of catalog.areas) {
    for (const p of a.parameters) {
      rows.push({
        area_id: a.id,
        area_title: a.title,
        key: p.stable_id,
        name_it: p.name_it,
        technical_name: p.technical_name,
        json_path: p.json_path,
        endpoint: p.endpoint,
        description_it: p.description_it,
        tooltip_it: p.tooltip_it ?? '',
        api_status: p.api_label || 'trovato_in_scan',
        db_status: p.db_status,
        model_v04_status: p.model_v04_status,
        implementation_status: '',
        useful_markets: '',
        difficulty: '',
        sample_value: sampleValueAsExportString(p.sample_value),
        sample_type: p.sample_type,
        is_selected: selectedIds.has(p.stable_id) ? 'true' : 'false',
      })
    }
  }
  return rows
}

const CSV_HEADERS: (keyof CatalogCsvRow)[] = [
  'area_id',
  'area_title',
  'key',
  'name_it',
  'technical_name',
  'json_path',
  'endpoint',
  'description_it',
  'tooltip_it',
  'api_status',
  'db_status',
  'model_v04_status',
  'implementation_status',
  'useful_markets',
  'difficulty',
  'sample_value',
  'sample_type',
  'is_selected',
]

function escapeCsvCell(value: string): string {
  const needsQuote = /[",\r\n]/.test(value)
  const escaped = value.replace(/"/g, '""')
  return needsQuote ? `"${escaped}"` : escaped
}

export function catalogCsvString(rows: CatalogCsvRow[]): string {
  const lines = [CSV_HEADERS.join(',')]
  for (const row of rows) {
    const cells = CSV_HEADERS.map((h) => escapeCsvCell(String(row[h] ?? '')))
    lines.push(cells.join(','))
  }
  return lines.join('\r\n')
}

export function downloadJson(filename: string, data: unknown): void {
  const body = JSON.stringify(data, null, 2)
  const blob = new Blob([body], { type: 'application/json;charset=utf-8' })
  triggerDownload(blob, filename)
}

export function downloadCsv(filename: string, rows: CatalogCsvRow[]): void {
  const body = `\ufeff${catalogCsvString(rows)}`
  const blob = new Blob([body], { type: 'text/csv;charset=utf-8' })
  triggerDownload(blob, filename)
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
