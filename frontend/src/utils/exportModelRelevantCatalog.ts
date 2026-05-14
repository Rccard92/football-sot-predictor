import type { ModelRelevantArea, ModelRelevantCatalogResponse, ModelRelevantField } from '../lib/api'
import { formatCatalogExportDate, sampleValueAsExportString, downloadJson } from './exportCatalog'

function escapeCsvCellLocal(value: string): string {
  const needsQuote = /[",\r\n]/.test(value)
  const escaped = value.replace(/"/g, '""')
  return needsQuote ? `"${escaped}"` : escaped
}

/** Righe visibili (stessi filtri UI) per export “filtrato”. */
export function filterModelRelevantField(
  f: ModelRelevantField,
  catalog: ModelRelevantCatalogResponse,
  o: {
    q: string
    areaId: string
    endpoint: string
    classification: string
    priority: string
    dbStatus: string
    modelV04: string
    sampleType: string
    onlyV04: boolean
  },
): boolean {
  const q = o.q.trim().toLowerCase()
  if (q) {
    const blob = `${f.name_it} ${f.json_path} ${f.endpoint} ${f.reason ?? ''} ${f.technical_name}`.toLowerCase()
    if (!blob.includes(q)) return false
  }
  if (o.areaId !== 'all') {
    const a = catalog.areas.find((x) => x.id === o.areaId)
    if (!a || f.area !== a.title) return false
  }
  if (o.endpoint.trim() && !f.endpoint.toLowerCase().includes(o.endpoint.trim().toLowerCase())) return false
  if (o.classification !== 'all' && f.classification !== o.classification) return false
  if (o.priority !== 'all' && (f.priority ?? '') !== o.priority) return false
  if (o.dbStatus !== 'all' && (f.db_status ?? '') !== o.dbStatus) return false
  if (o.modelV04 !== 'all' && f.model_v04_status !== o.modelV04) return false
  if (o.sampleType !== 'all' && f.sample_type !== o.sampleType) return false
  if (o.onlyV04 && f.model_v04_status !== 'used_v04') return false
  return true
}

export function countSelectedModelFields(catalog: ModelRelevantCatalogResponse, selectedIds: Set<string>): number {
  let n = 0
  for (const a of catalog.areas) {
    for (const p of a.parameters) {
      if (selectedIds.has(p.key)) n++
    }
  }
  return n
}

export type ModelRelevantCsvRow = {
  section: string
  area_id: string
  area_title: string
  key: string
  name_it: string
  technical_name: string
  json_path: string
  endpoint: string
  description: string
  classification: string
  priority: string
  recommended_markets: string
  model_v04_status: string
  db_status: string
  sample_type: string
  sample_value: string
  is_selected: string
}

const MR_CSV_HEADERS: (keyof ModelRelevantCsvRow)[] = [
  'section',
  'area_id',
  'area_title',
  'key',
  'name_it',
  'technical_name',
  'json_path',
  'endpoint',
  'description',
  'classification',
  'priority',
  'recommended_markets',
  'model_v04_status',
  'db_status',
  'sample_type',
  'sample_value',
  'is_selected',
]

function modelRelevantCsvString(rows: ModelRelevantCsvRow[]): string {
  const lines = [MR_CSV_HEADERS.join(',')]
  for (const row of rows) {
    const cells = MR_CSV_HEADERS.map((h) => escapeCsvCellLocal(String(row[h] ?? '')))
    lines.push(cells.join(','))
  }
  return lines.join('\r\n')
}

export function downloadModelRelevantCsv(filename: string, rows: ModelRelevantCsvRow[]): void {
  const body = `\ufeff${modelRelevantCsvString(rows)}`
  const blob = new Blob([body], { type: 'text/csv;charset=utf-8' })
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

function areaSlugForField(catalog: ModelRelevantCatalogResponse, areaTitle: string): string {
  const a = catalog.areas.find((x) => x.title === areaTitle)
  return a?.id ?? areaTitle
}

function flattenVisibleToCsvRows(
  catalog: ModelRelevantCatalogResponse,
  visibleAreas: { area: ModelRelevantArea; parameters: ModelRelevantField[] }[],
  visibleTechnical: ModelRelevantField[],
  selectedIds: Set<string>,
): ModelRelevantCsvRow[] {
  const rows: ModelRelevantCsvRow[] = []
  for (const { area, parameters } of visibleAreas) {
    for (const p of parameters) {
      rows.push({
        section: 'modello',
        area_id: area.id,
        area_title: area.title,
        key: p.key,
        name_it: p.name_it,
        technical_name: p.technical_name,
        json_path: p.json_path,
        endpoint: p.endpoint,
        description: p.reason ?? '',
        classification: p.classification,
        priority: p.priority ?? '',
        recommended_markets: (p.recommended_markets ?? '').replace(/;/g, ';'),
        model_v04_status: p.model_v04_status,
        db_status: p.db_status ?? '',
        sample_type: p.sample_type,
        sample_value: sampleValueAsExportString(p.sample_value),
        is_selected: selectedIds.has(p.key) ? 'true' : 'false',
      })
    }
  }
  for (const p of visibleTechnical) {
    rows.push({
      section: 'fonti_tecniche',
      area_id: areaSlugForField(catalog, p.area),
      area_title: p.area,
      key: p.key,
      name_it: p.name_it,
      technical_name: p.technical_name,
      json_path: p.json_path,
      endpoint: p.endpoint,
      description: p.reason ?? '',
      classification: p.classification,
      priority: p.priority ?? '',
      recommended_markets: p.recommended_markets ?? '',
      model_v04_status: p.model_v04_status,
      db_status: p.db_status ?? '',
      sample_type: p.sample_type,
      sample_value: sampleValueAsExportString(p.sample_value),
      is_selected: 'false',
    })
  }
  return rows
}

export function buildModelRelevantFilteredExportPayload(
  catalog: ModelRelevantCatalogResponse,
  visibleAreas: { area: ModelRelevantArea; parameters: ModelRelevantField[] }[],
  visibleTechnical: ModelRelevantField[],
  selectedIds: Set<string>,
): Record<string, unknown> {
  const modelCount = visibleAreas.reduce((acc, x) => acc + x.parameters.length, 0)
  const selectedInView = visibleAreas.reduce(
    (acc, x) => acc + x.parameters.filter((p) => selectedIds.has(p.key)).length,
    0,
  )
  return {
    exported_at: new Date().toISOString(),
    catalog_version: catalog.version,
    message: catalog.message ?? null,
    source: catalog.source,
    summary: {
      ...catalog.summary,
      exported_model_field_rows: modelCount,
      exported_technical_field_rows: visibleTechnical.length,
      selected_in_export_view: selectedInView,
    },
    areas: visibleAreas.map(({ area, parameters }) => ({
      id: area.id,
      title: area.title,
      parameters: parameters.map((p) => ({
        ...p,
        is_selected: selectedIds.has(p.key),
      })),
    })),
    technical_derivative_sources: {
      title: catalog.technical_derivative_sources.title,
      fields: visibleTechnical.map((f) => ({ ...f, is_selected: false })),
    },
  }
}

export function buildModelRelevantSelectedExportPayload(
  catalog: ModelRelevantCatalogResponse,
  selectedIds: Set<string>,
): Record<string, unknown> {
  const parameters: Record<string, unknown>[] = []
  for (const a of catalog.areas) {
    for (const p of a.parameters) {
      if (selectedIds.has(p.key)) parameters.push({ ...p, is_selected: true })
    }
  }
  return {
    exported_at: new Date().toISOString(),
    catalog_version: catalog.version,
    count: parameters.length,
    parameters,
  }
}

export function exportModelRelevantFilteredJson(
  catalog: ModelRelevantCatalogResponse,
  visibleAreas: { area: ModelRelevantArea; parameters: ModelRelevantField[] }[],
  visibleTechnical: ModelRelevantField[],
  selectedIds: Set<string>,
): void {
  const dateStr = formatCatalogExportDate()
  downloadJson(
    `api-football-model-catalog-${dateStr}.json`,
    buildModelRelevantFilteredExportPayload(catalog, visibleAreas, visibleTechnical, selectedIds),
  )
}

export function exportModelRelevantFilteredCsv(
  catalog: ModelRelevantCatalogResponse,
  visibleAreas: { area: ModelRelevantArea; parameters: ModelRelevantField[] }[],
  visibleTechnical: ModelRelevantField[],
  selectedIds: Set<string>,
): void {
  const rows = flattenVisibleToCsvRows(catalog, visibleAreas, visibleTechnical, selectedIds)
  downloadModelRelevantCsv(`api-football-model-catalog-${formatCatalogExportDate()}.csv`, rows)
}

export function exportModelRelevantSelectedJson(catalog: ModelRelevantCatalogResponse, selectedIds: Set<string>): void {
  downloadJson(
    `api-football-model-selected-fields-${formatCatalogExportDate()}.json`,
    buildModelRelevantSelectedExportPayload(catalog, selectedIds),
  )
}
