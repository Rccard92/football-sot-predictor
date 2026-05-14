/**
 * Deduplicazione viste catalogo model-relevant (solo UI): stesso campo logico da endpoint diversi.
 */

import type { ModelRelevantField } from '../lib/api'
import { getCatalogFieldDisplayName, getCatalogFieldGroup, getSemanticGroupTitle } from './catalogFieldLabels'

/** Priorità endpoint: indice minore = primario. */
const ENDPOINT_PRIORITY = [
  'fixtures',
  'fixtures/statistics',
  'teams/statistics',
  'fixtures/players',
  'fixtures/events',
  'fixtures/lineups',
  'standings',
  'injuries',
  'odds',
  'predictions',
  'fixtures/headtohead',
] as const

/** Priorità dedupe solo gruppo «Tiri» (volume). */
const TIRI_ENDPOINT_PRIORITY = [
  'fixtures/statistics',
  'teams/statistics',
  'fixtures/players',
  'players',
  'players/statistics',
  'fixtures/headtohead',
] as const

export type CatalogAlternativeSource = {
  endpoint: string
  stable_id: string
  json_path: string
}

function endpointRank(field: ModelRelevantField): number {
  const e = (field.endpoint || '').trim().toLowerCase()
  const list =
    getCatalogFieldGroup(field) === 'tiri'
      ? (TIRI_ENDPOINT_PRIORITY as readonly string[])
      : (ENDPOINT_PRIORITY as readonly string[])
  const i = list.indexOf(e)
  return i === -1 ? list.length : i
}

function normJsonPath(f: ModelRelevantField): string {
  return (f.original_json_path || f.json_path || '').toLowerCase().trim()
}

/**
 * Chiave logica: stesso json_path + titolo gruppo IT + titolo display (tutti e tre come da specifica).
 */
export function catalogDedupeCanonicalKey(f: ModelRelevantField): string {
  const gid = getCatalogFieldGroup(f)
  const path = normJsonPath(f)
  const disp = getCatalogFieldDisplayName(f).trim().toLowerCase()
  const groupIt = getSemanticGroupTitle(gid).trim().toLowerCase()
  return `${groupIt}::${path}::${disp}`
}

export function isCatalogFieldSelected(f: ModelRelevantField, selectedIds: Set<string>): boolean {
  const keys = f.merged_catalog_keys ?? [f.key]
  return keys.some((k) => selectedIds.has(k))
}

/**
 * Unisce righe duplicate; sul primario imposta merged_catalog_keys, alternative_sources, dedupe_search_blob.
 */
export function deduplicateCatalogFields(fields: ModelRelevantField[]): ModelRelevantField[] {
  const map = new Map<string, ModelRelevantField[]>()
  for (const f of fields) {
    const ck = catalogDedupeCanonicalKey(f)
    if (!map.has(ck)) map.set(ck, [])
    map.get(ck)!.push(f)
  }
  const out: ModelRelevantField[] = []
  for (const group of map.values()) {
    if (group.length === 1) {
      out.push(group[0]!)
      continue
    }
    const sorted = [...group].sort((a, b) => {
      const ra = endpointRank(a)
      const rb = endpointRank(b)
      if (ra !== rb) return ra - rb
      return a.key.localeCompare(b.key)
    })
    const primary = sorted[0]!
    const alts: CatalogAlternativeSource[] = sorted.slice(1).map((x) => ({
      endpoint: x.endpoint,
      stable_id: x.key,
      json_path: x.json_path,
    }))
    const merged_catalog_keys = sorted.map((x) => x.key)
    const dedupe_search_blob = sorted.map((x) => `${x.endpoint} ${x.key} ${x.json_path}`).join(' ')
    out.push({
      ...primary,
      merged_catalog_keys,
      alternative_sources: alts,
      dedupe_search_blob,
    })
  }
  return out
}
