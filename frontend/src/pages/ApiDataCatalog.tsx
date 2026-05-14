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
import { ModelRelevantTechnicalSection } from '../components/catalog/ModelRelevantTechnicalSection'
import {
  exportModelRelevantFilteredCsv,
  exportModelRelevantFilteredJson,
  exportModelRelevantSelectedJson,
  filterModelRelevantField,
  countSelectedModelFields,
} from '../utils/exportModelRelevantCatalog'
import { formatCatalogExportDate } from '../utils/exportCatalog'

const TECH_SECTION_ID = 'technical_derivative'

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
    }),
    [search, areaId, endpoint, classification, priority, dbStatus, modelV04, sampleType, onlyV04],
  )

  const loadCatalog = useCallback(async () => {
    const res = await getApiFootballModelRelevantCatalog()
    setCatalog(res)
    const om: Record<string, boolean> = { [TECH_SECTION_ID]: true }
    for (const a of res.areas) {
      om[a.id] = true
    }
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

  const areaOptions = useMemo(
    () => (catalog ? catalog.areas.map((a) => ({ id: a.id, title: a.title })) : []),
    [catalog],
  )

  const classificationOptions = useMemo(() => {
    if (!catalog) return []
    const s = new Set<string>()
    for (const a of catalog.areas) {
      for (const p of a.parameters) {
        s.add(p.classification)
      }
    }
    s.add('SORGENTE_DERIVATA_TECNICA')
    return [...s].sort()
  }, [catalog])

  const visibleAreas = useMemo(() => {
    if (!catalog) return []
    return catalog.areas.map((area) => ({
      area,
      parameters: area.parameters.filter((p) => filterModelRelevantField(p, catalog, filterOpts)),
    }))
  }, [catalog, filterOpts])

  const visibleTechnical = useMemo(() => {
    if (!catalog) return []
    return catalog.technical_derivative_sources.fields.filter((p) =>
      filterModelRelevantField(p, catalog, filterOpts),
    )
  }, [catalog, filterOpts])

  const visibleCount = useMemo(() => {
    const m = visibleAreas.reduce((acc, x) => acc + x.parameters.length, 0)
    return m + visibleTechnical.length
  }, [visibleAreas, visibleTechnical])

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

  const toggleSelect = useCallback((key: string) => {
    setSelectedIds((prev) => {
      const n = new Set(prev)
      if (n.has(key)) n.delete(key)
      else n.add(key)
      return n
    })
  }, [])

  const clearSel = useCallback(() => setSelectedIds(new Set()), [])

  const sum = catalog?.summary

  const exportJson = () => {
    if (!catalog) return
    exportModelRelevantFilteredJson(catalog, visibleAreas, visibleTechnical, selectedIds)
  }
  const exportCsv = () => {
    if (!catalog) return
    exportModelRelevantFilteredCsv(catalog, visibleAreas, visibleTechnical, selectedIds)
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

      <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950">
        <p className="font-medium">Catalogo model-relevant</p>
        <p className="mt-1 text-sky-900">
          Le voci classificate come da nascondere in tab modello non compaiono. Le &quot;fonti tecniche&quot; sono
          strumentali alle derivate ma non sono selezionabili come feature dirette.
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
              <span className="font-semibold text-slate-800">{visibleCount}</span> righe (modello + fonti tecniche).
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
          />

          <div className="space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Variabili modello</h2>
            {visibleAreas.map(({ area, parameters }) => (
              <ModelRelevantAreaSection
                key={area.id}
                area={area}
                parameters={parameters}
                open={openMap[area.id] ?? false}
                onToggle={() => toggleOpen(area.id)}
                showCheckbox
                selectedIds={selectedIds}
                onToggleSelect={toggleSelect}
              />
            ))}
          </div>

          <ModelRelevantTechnicalSection
            title={catalog.technical_derivative_sources.title}
            fields={visibleTechnical}
            open={openMap[TECH_SECTION_ID] ?? true}
            onToggle={() => toggleOpen(TECH_SECTION_ID)}
          />
        </>
      ) : !error ? (
        <p className="text-sm text-slate-600">Caricamento…</p>
      ) : null}
    </div>
  )
}
