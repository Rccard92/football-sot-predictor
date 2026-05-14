import type { ModelRelevantCatalogResponse, ModelRelevantField } from '../lib/api'
import type { SemanticGroupSection } from './catalogFieldLabels'
import {
  getCatalogFieldDescription,
  getCatalogFieldDisplayName,
  getCatalogFieldGroup,
  getSemanticGroupTitle,
} from './catalogFieldLabels'
import { formatCatalogExportDate, sampleValueAsExportString, downloadJson } from './exportCatalog'
import { isCatalogFieldSelected } from './deduplicateCatalogFields'

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
    semanticGroup: string
  },
  opts?: { skipQuery?: boolean },
): boolean {
  const q = o.q.trim().toLowerCase()
  if (!opts?.skipQuery && q) {
    const g = getCatalogFieldGroup(f)
    const blob = [
      f.name_it,
      f.json_path,
      f.endpoint,
      f.reason ?? '',
      f.technical_name,
      getCatalogFieldDisplayName(f),
      getCatalogFieldDescription(f),
      getSemanticGroupTitle(g),
      f.dedupe_search_blob ?? '',
    ]
      .join(' ')
      .toLowerCase()
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
  if (o.semanticGroup !== 'all' && getCatalogFieldGroup(f) !== o.semanticGroup) return false
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
  semantic_group_id: string
  semantic_group_it: string
  display_name_it: string
  display_description_it: string
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
  merged_catalog_keys: string
  alternative_sources_json: string
}

const MR_CSV_HEADERS: (keyof ModelRelevantCsvRow)[] = [
  'section',
  'area_id',
  'area_title',
  'semantic_group_id',
  'semantic_group_it',
  'display_name_it',
  'display_description_it',
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
  'merged_catalog_keys',
  'alternative_sources_json',
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

function enrichParam(p: ModelRelevantField, selectedIds: Set<string>) {
  const gid = getCatalogFieldGroup(p)
  return {
    ...p,
    display_name_it: getCatalogFieldDisplayName(p),
    display_description_it: getCatalogFieldDescription(p),
    semantic_group_it: getSemanticGroupTitle(gid),
    semantic_group_id: gid,
    is_selected: isCatalogFieldSelected(p, selectedIds),
    merged_catalog_keys: p.merged_catalog_keys,
    alternative_sources: p.alternative_sources,
  }
}

function flattenVisibleToCsvRows(
  visibleSections: SemanticGroupSection[],
  selectedIds: Set<string>,
): ModelRelevantCsvRow[] {
  const rows: ModelRelevantCsvRow[] = []
  for (const sec of visibleSections) {
    for (const p of sec.parameters) {
      const isTech = p.classification === 'SORGENTE_DERIVATA_TECNICA'
      rows.push({
        section: isTech ? 'fonti_tecniche' : 'modello',
        area_id: sec.id,
        area_title: sec.title,
        semantic_group_id: sec.id,
        semantic_group_it: sec.title,
        display_name_it: getCatalogFieldDisplayName(p),
        display_description_it: getCatalogFieldDescription(p),
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
        is_selected: isCatalogFieldSelected(p, selectedIds) ? 'true' : 'false',
        merged_catalog_keys: (p.merged_catalog_keys ?? [p.key]).join(' | '),
        alternative_sources_json: p.alternative_sources?.length
          ? JSON.stringify(p.alternative_sources)
          : '',
      })
    }
  }
  return rows
}

export function buildModelRelevantFilteredExportPayload(
  catalog: ModelRelevantCatalogResponse,
  visibleSections: SemanticGroupSection[],
  selectedIds: Set<string>,
): Record<string, unknown> {
  const modelCount = visibleSections.reduce((acc, x) => acc + x.parameters.length, 0)
  const selectedInView = visibleSections.reduce(
    (acc, x) => acc + x.parameters.filter((p) => isCatalogFieldSelected(p, selectedIds)).length,
    0,
  )
  return {
    exported_at: new Date().toISOString(),
    catalog_version: catalog.version,
    message: catalog.message ?? null,
    source: catalog.source,
    summary: {
      ...catalog.summary,
      exported_field_rows: modelCount,
      selected_in_export_view: selectedInView,
    },
    semantic_groups: visibleSections.map(({ id, title, parameters }) => ({
      id,
      title,
      parameters: parameters.map((p) => enrichParam(p, selectedIds)),
    })),
  }
}

export function buildModelRelevantSelectedExportPayload(
  catalog: ModelRelevantCatalogResponse,
  selectedIds: Set<string>,
): Record<string, unknown> {
  const parameters: Record<string, unknown>[] = []
  for (const a of catalog.areas) {
    for (const p of a.parameters) {
      if (selectedIds.has(p.key)) parameters.push(enrichParam(p, selectedIds))
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
  visibleSections: SemanticGroupSection[],
  selectedIds: Set<string>,
): void {
  const dateStr = formatCatalogExportDate()
  downloadJson(
    `api-football-model-catalog-${dateStr}.json`,
    buildModelRelevantFilteredExportPayload(catalog, visibleSections, selectedIds),
  )
}

export function exportModelRelevantFilteredCsv(
  visibleSections: SemanticGroupSection[],
  selectedIds: Set<string>,
): void {
  const rows = flattenVisibleToCsvRows(visibleSections, selectedIds)
  downloadModelRelevantCsv(`api-football-model-catalog-${formatCatalogExportDate()}.csv`, rows)
}

export function exportModelRelevantSelectedJson(catalog: ModelRelevantCatalogResponse, selectedIds: Set<string>): void {
  downloadJson(
    `api-football-model-selected-fields-${formatCatalogExportDate()}.json`,
    buildModelRelevantSelectedExportPayload(catalog, selectedIds),
  )
}
