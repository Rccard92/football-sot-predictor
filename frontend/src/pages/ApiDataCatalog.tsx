import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getApiFootballModelRelevantCatalog,
  type ModelRelevantCatalogResponse,
  type ModelRelevantField,
} from '../lib/api'
import { Card } from '../components/ui/Card'
import { ModelRelevantAreaSection } from '../components/catalog/ModelRelevantAreaSection'
import { ModelRelevantFilters } from '../components/catalog/ModelRelevantFilters'
import {
  ModelRelevantSelectedPanel,
  loadModelRelevantSelected,
  persistModelRelevantSelected,
} from '../components/catalog/ModelRelevantSelectedPanel'
import {
  exportModelRelevantFilteredCsv,
  exportModelRelevantFilteredJson,
  exportModelRelevantSelectedJson,
  filterModelRelevantField,
  countSelectedModelFields,
} from '../utils/exportModelRelevantCatalog'
import { formatCatalogExportDate } from '../utils/exportCatalog'
import {
  SEMANTIC_GROUP_ORDER,
  countV04Stats,
  getCatalogFieldDescription,
  getCatalogFieldDisplayName,
  getCatalogFieldGroup,
  getSemanticGroupTitle,
  groupFieldsBySemanticOrder,
  semanticGroupOptionsForFilter,
  type SemanticGroupSection,
} from '../utils/catalogFieldLabels'
import { deduplicateCatalogFields } from '../utils/deduplicateCatalogFields'
import { RefereeDiscoveryPanel } from '../components/admin/RefereeDiscoveryPanel'

export function ApiDataCatalog() {
  const [catalog, setCatalog] = useState<ModelRelevantCatalogResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [areaId, setAreaId] = useState('all')
  const [endpoint, setEndpoint] = useState('')
  const [classification, setClassification] = useState('all')
  const [priority, setPriority] = useState('all')
  const [dbStatus, setDbStatus] = useState('all')
  const [modelV04, setModelV04] = useState('all')
  const [sampleType, setSampleType] = useState('all')
  const [onlyV04, setOnlyV04] = useState(false)
  const [semanticGroup, setSemanticGroup] = useState('all')

  const [openMap, setOpenMap] = useState<Record<string, boolean>>({})
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => loadModelRelevantSelected())

  const filterOpts = useMemo(
    () => ({
      q: search,
      areaId,
      endpoint,
      classification,
      priority,
      dbStatus,
      modelV04,
      sampleType,
      onlyV04,
      semanticGroup,
    }),
    [search, areaId, endpoint, classification, priority, dbStatus, modelV04, sampleType, onlyV04, semanticGroup],
  )

  const loadCatalog = useCallback(async () => {
    const res = await getApiFootballModelRelevantCatalog()
    setCatalog(res)
    const om: Record<string, boolean> = {}
    for (const id of SEMANTIC_GROUP_ORDER) om[id] = true
    setOpenMap(om)
  }, [])

  useEffect(() => {
    let c = false
    ;(async () => {
      try {
        await loadCatalog()
        if (!c) setError(null)
      } catch (e) {
        if (!c) setError(e instanceof Error ? e.message : 'Errore caricamento')
      }
    })()
    return () => {
      c = true
    }
  }, [loadCatalog])

  useEffect(() => {
    persistModelRelevantSelected(selectedIds)
  }, [selectedIds])

  const technicalKeys = useMemo(() => {
    const s = new Set<string>()
    if (!catalog) return s
    for (const p of catalog.technical_derivative_sources.fields) s.add(p.key)
    return s
  }, [catalog])

  const areaOptions = useMemo(
    () => (catalog ? catalog.areas.map((a) => ({ id: a.id, title: a.title })) : []),
    [catalog],
  )

  const semanticGroupOptions = useMemo(() => semanticGroupOptionsForFilter(), [])

  const classificationOptions = useMemo(() => {
    if (!catalog) return []
    const s = new Set<string>()
    for (const a of catalog.areas) {
      for (const p of a.parameters) {
        s.add(p.classification)
      }
    }
    for (const p of catalog.technical_derivative_sources.fields) {
      s.add(p.classification)
    }
    return [...s].sort()
  }, [catalog])

  const flatStructural = useMemo(() => {
    if (!catalog) return []
    const out: ModelRelevantField[] = []
    for (const a of catalog.areas) {
      for (const p of a.parameters) {
        if (filterModelRelevantField(p, catalog, filterOpts, { skipQuery: true })) out.push(p)
      }
    }
    for (const p of catalog.technical_derivative_sources.fields) {
      if (filterModelRelevantField(p, catalog, filterOpts, { skipQuery: true })) out.push(p)
    }
    return out
  }, [catalog, filterOpts])

  const flatDeduped = useMemo(() => deduplicateCatalogFields(flatStructural), [flatStructural])

  const flatFiltered = useMemo(() => {
    const q = filterOpts.q.trim().toLowerCase()
    if (!q) return flatDeduped
    return flatDeduped.filter((f) => {
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
      return blob.includes(q)
    })
  }, [flatDeduped, filterOpts.q])

  const visibleSemanticSections = useMemo(() => {
    const base = groupFieldsBySemanticOrder(flatFiltered)
    const goal = base.find((s) => s.id === 'goal_over_under')
    const rest = base.filter((s) => s.id !== 'goal_over_under')
    const ordered: SemanticGroupSection[] = goal ? [goal, ...rest] : base
    return ordered
  }, [flatFiltered])

  const visibleCount = flatFiltered.length

  const fieldsByKey = useMemo(() => {
    const m = new Map<string, ModelRelevantField>()
    if (!catalog) return m
    for (const a of catalog.areas) {
      for (const p of a.parameters) {
        m.set(p.key, p)
      }
    }
    return m
  }, [catalog])

  const selectedInCatalogCount = catalog ? countSelectedModelFields(catalog, selectedIds) : 0

  const toggleOpen = useCallback((id: string) => {
    setOpenMap((prev) => ({ ...prev, [id]: !prev[id] }))
  }, [])

  const toggleSelectMerged = useCallback((field: ModelRelevantField) => {
    const keys = field.merged_catalog_keys ?? [field.key]
    setSelectedIds((prev) => {
      const n = new Set(prev)
      const any = keys.some((k) => n.has(k))
      if (any) {
        for (const k of keys) n.delete(k)
      } else {
        n.add(keys[0]!)
      }
      return n
    })
  }, [])

  const clearSel = useCallback(() => setSelectedIds(new Set()), [])

  const sum = catalog?.summary

  const exportJson = () => {
    if (!catalog) return
    exportModelRelevantFilteredJson(catalog, visibleSemanticSections, selectedIds)
  }
  const exportCsv = () => {
    if (!catalog) return
    exportModelRelevantFilteredCsv(visibleSemanticSections, selectedIds)
  }
  const exportSelected = () => {
    if (!catalog) return
    exportModelRelevantSelectedJson(catalog, selectedIds)
  }

  const exportDateStr = formatCatalogExportDate()
  const exportJsonFilenameHint = `api-football-model-catalog-${exportDateStr}.json`

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Catalogo dati API</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Variabili API-Football classificate per rilevanza statistica e uso nel modello (catalogo statico curato). Nessuna
          chiamata al provider al caricamento della pagina.
        </p>
      </header>

      <RefereeDiscoveryPanel />

      <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950">
        <p className="font-medium">Catalogo model-relevant</p>
        <p className="mt-1 text-sky-900">
          Le voci classificate come da nascondere in tab modello non compaiono. Le fonti tecniche derivate sono incluse nel
          gruppo statistico pertinente (di solito &quot;Contesto tecnico / fonti derivate&quot;) con checkbox disabilitate.
        </p>
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">{error}</div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void loadCatalog()}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 shadow-sm"
        >
          Ricarica catalogo
        </button>
      </div>

      {catalog?.message ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">{catalog.message}</div>
      ) : null}

      {catalog ? (
        <>
          <Card title="Riepilogo catalogo modello">
            <p className="mb-3 text-xs text-slate-500">
              Conteggi globali dal file sorgente. Con i filtri attivi sono visibili{' '}
              <span className="font-semibold text-slate-800">{visibleCount}</span> righe (catalogo modello + fonti
              tecniche, raggruppate per gruppo statistico).
            </p>
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <dt className="text-xs font-medium text-slate-500">Macro-aree</dt>
                <dd className="text-lg font-semibold text-slate-900">{sum?.area_count ?? 0}</dd>
              </div>
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <dt className="text-xs font-medium text-slate-500">Campi catalogo modello</dt>
                <dd className="text-lg font-semibold text-slate-900">{sum?.model_field_count ?? 0}</dd>
              </div>
              <div className="rounded-xl bg-amber-50 px-3 py-2">
                <dt className="text-xs font-medium text-amber-800">Fonti tecniche (derivate)</dt>
                <dd className="text-lg font-semibold text-amber-950">{sum?.technical_derivative_count ?? 0}</dd>
              </div>
              <div className="rounded-xl bg-violet-50 px-3 py-2">
                <dt className="text-xs font-medium text-violet-800">Usati da v0.4 (nel catalogo)</dt>
                <dd className="text-lg font-semibold text-violet-950">{sum?.fields_used_by_v04_in_model_catalog ?? 0}</dd>
              </div>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
              <button
                type="button"
                onClick={exportJson}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50"
              >
                Esporta JSON (vista filtrata)
              </button>
              <button
                type="button"
                onClick={exportCsv}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50"
              >
                Esporta CSV (vista filtrata)
              </button>
              <button
                type="button"
                onClick={exportSelected}
                disabled={selectedInCatalogCount === 0}
                title={
                  selectedInCatalogCount === 0
                    ? 'Seleziona almeno un campo del catalogo modello con le checkbox.'
                    : undefined
                }
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Esporta selezionati (JSON)
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              JSON e CSV riflettono i filtri attuali (non il catalogo grezzo da scan). File JSON tipico:{' '}
              <span className="font-mono">{exportJsonFilenameHint}</span>.
            </p>
          </Card>

          <ModelRelevantSelectedPanel selectedIds={selectedIds} fieldsByKey={fieldsByKey} onClear={clearSel} />

          <ModelRelevantFilters
            search={search}
            onSearchChange={setSearch}
            areaId={areaId}
            onAreaIdChange={setAreaId}
            areaOptions={areaOptions}
            endpoint={endpoint}
            onEndpointChange={setEndpoint}
            classification={classification}
            onClassificationChange={setClassification}
            classificationOptions={classificationOptions}
            priority={priority}
            onPriorityChange={setPriority}
            dbStatus={dbStatus}
            onDbStatusChange={setDbStatus}
            modelV04={modelV04}
            onModelV04Change={setModelV04}
            sampleType={sampleType}
            onSampleTypeChange={setSampleType}
            onlyV04={onlyV04}
            onOnlyV04Change={setOnlyV04}
            semanticGroup={semanticGroup}
            onSemanticGroupChange={setSemanticGroup}
            semanticGroupOptions={semanticGroupOptions}
          />

          <div className="space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Gruppi statistici</h2>
            {visibleSemanticSections.length === 0 ? (
              <p className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Nessun campo corrisponde ai filtri attuali.
              </p>
            ) : (
              visibleSemanticSections.map((sec) => (
              <ModelRelevantAreaSection
                key={sec.id}
                title={sec.title}
                subtitle={sec.sectionSubtitle}
                parameters={sec.parameters}
                open={openMap[sec.id] ?? false}
                onToggle={() => toggleOpen(sec.id)}
                technicalKeys={technicalKeys}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelectMerged}
                headerStats={countV04Stats(sec.parameters)}
                subsections={sec.subsections}
                sectionReviewPending={sec.sectionReviewPending}
              />
            ))
            )}
          </div>
        </>
      ) : !error ? (
        <p className="text-sm text-slate-600">Caricamento…</p>
      ) : null}
    </div>
  )
}
