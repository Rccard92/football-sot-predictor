import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  DEFAULT_SEASON,
  getApiFootballCatalogDirect,
  postAdminDebugApiFootballCatalogScan,
  type ApiFootballDirectCatalogResponse,
  type ApiFootballDirectField,
  type ApiFootballScanDiagnostic,
} from '../lib/api'
import { Card } from '../components/ui/Card'
import { DirectCatalogAreaSection } from '../components/catalog/DirectCatalogAreaSection'
import { DirectCatalogFilters } from '../components/catalog/DirectCatalogFilters'
import {
  DirectSelectedFieldsPanel,
  loadSelectedDirectFields,
  persistSelectedDirectFields,
} from '../components/catalog/DirectSelectedFieldsPanel'
import { DirectScanDiagnosticsTable } from '../components/catalog/DirectScanDiagnostics'

type UiMode = 'catalog' | 'diagnostics'

function matches(
  p: ApiFootballDirectField,
  o: {
    q: string
    areaId: string
    endpoint: string
    dbStatus: string
    modelV04: string
    sampleType: string
    onlyV04: boolean
    onlyNotSavedDb: boolean
    onlyWithTooltip: boolean
    onlyNumeric: boolean
  },
): boolean {
  const q = o.q.trim().toLowerCase()
  if (q) {
    const blob = `${p.name_it} ${p.json_path} ${p.endpoint} ${p.description_it}`.toLowerCase()
    if (!blob.includes(q)) return false
  }
  if (o.areaId !== 'all' && p.area_id !== o.areaId) return false
  if (o.endpoint.trim() && !p.endpoint.toLowerCase().includes(o.endpoint.trim().toLowerCase())) return false
  if (o.dbStatus !== 'all' && p.db_status !== o.dbStatus) return false
  if (o.modelV04 !== 'all' && p.model_v04_status !== o.modelV04) return false
  if (o.sampleType !== 'all' && p.sample_type !== o.sampleType) return false
  if (o.onlyV04 && p.model_v04_status !== 'used_v04') return false
  if (o.onlyNotSavedDb && (p.db_status === 'saved_column' || p.db_status === 'raw_json_only')) return false
  if (o.onlyWithTooltip && !p.tooltip_it) return false
  if (o.onlyNumeric && p.sample_type !== 'numero' && p.sample_type !== 'percentuale') return false
  return true
}

export function ApiDataCatalog() {
  const [mode, setMode] = useState<UiMode>('catalog')
  const [catalog, setCatalog] = useState<ApiFootballDirectCatalogResponse | null>(null)
  const [diagnostics, setDiagnostics] = useState<ApiFootballScanDiagnostic[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scanBusy, setScanBusy] = useState(false)

  const [search, setSearch] = useState('')
  const [areaId, setAreaId] = useState('all')
  const [endpoint, setEndpoint] = useState('')
  const [dbStatus, setDbStatus] = useState('all')
  const [modelV04, setModelV04] = useState('all')
  const [sampleType, setSampleType] = useState('all')
  const [onlyV04, setOnlyV04] = useState(false)
  const [onlyNotSavedDb, setOnlyNotSavedDb] = useState(false)
  const [onlyWithTooltip, setOnlyWithTooltip] = useState(false)
  const [onlyNumeric, setOnlyNumeric] = useState(false)

  const [openMap, setOpenMap] = useState<Record<string, boolean>>({})
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => loadSelectedDirectFields())

  const loadCatalog = useCallback(async () => {
    const res = await getApiFootballCatalogDirect()
    setCatalog(res)
    const om: Record<string, boolean> = {}
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
    persistSelectedDirectFields(selectedIds)
  }, [selectedIds])

  const fieldsByStable = useMemo(() => {
    const m = new Map<string, ApiFootballDirectField>()
    if (!catalog) return m
    for (const a of catalog.areas) {
      for (const p of a.parameters) {
        m.set(p.stable_id, p)
      }
    }
    return m
  }, [catalog])

  const areaOptions = useMemo(
    () => (catalog ? catalog.areas.map((a) => ({ id: a.id, title: a.title })) : []),
    [catalog],
  )

  const allFields = useMemo(() => {
    if (!catalog) return []
    return catalog.areas.flatMap((a) => a.parameters)
  }, [catalog])

  const filterOpts = useMemo(
    () => ({
      q: search,
      areaId,
      endpoint,
      dbStatus,
      modelV04,
      sampleType,
      onlyV04,
      onlyNotSavedDb,
      onlyWithTooltip,
      onlyNumeric,
    }),
    [search, areaId, endpoint, dbStatus, modelV04, sampleType, onlyV04, onlyNotSavedDb, onlyWithTooltip, onlyNumeric],
  )

  const filtered = useMemo(() => allFields.filter((p) => matches(p, filterOpts)), [allFields, filterOpts])

  const visibleCount = filtered.length

  const runScan = async () => {
    setScanBusy(true)
    setError(null)
    try {
      const res = await postAdminDebugApiFootballCatalogScan(DEFAULT_SEASON)
      const { diagnostics: d, ...rest } = res
      setDiagnostics(d ?? null)
      setCatalog(rest)
      setMode('diagnostics')
      const om: Record<string, boolean> = {}
      for (const a of rest.areas) {
        om[a.id] = true
      }
      setOpenMap(om)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scan fallito')
    } finally {
      setScanBusy(false)
    }
  }

  const toggleOpen = useCallback((id: string) => {
    setOpenMap((prev) => ({ ...prev, [id]: !prev[id] }))
  }, [])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }, [])

  const clearSel = useCallback(() => setSelectedIds(new Set()), [])

  const s = catalog?.summary

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Catalogo dati API</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Solo parametri trovati direttamente nelle response API-Football (ultimo scan). Nessuna variabile derivata dal
          modello (medie, trend, componenti) è elencata qui.
        </p>
      </header>

      <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950">
        <p className="font-medium">Dato diretto API vs variabile derivata</p>
        <p className="mt-1 text-sky-900">
          Questa pagina mostra solo i parametri recuperabili direttamente da API-Football. Le variabili derivate dal
          modello — come medie sulle ultime partite, trend, conversioni o componenti aggregati (es. offensive production)
          — non compaiono in questa tab. Esempi: tiri in porta da statistiche partita = diretto; media tiri in porta
          ultime 5 = derivata; precisione tiro = derivata.
        </p>
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">{error}</div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
          <button
            type="button"
            onClick={() => setMode('catalog')}
            className={`rounded-lg px-3 py-2 text-sm font-medium ${mode === 'catalog' ? 'bg-slate-900 text-white' : 'text-slate-700'}`}
          >
            Catalogo diretto API
          </button>
          <button
            type="button"
            onClick={() => setMode('diagnostics')}
            className={`rounded-lg px-3 py-2 text-sm font-medium ${mode === 'diagnostics' ? 'bg-slate-900 text-white' : 'text-slate-700'}`}
          >
            Diagnostica scan
          </button>
        </div>
        <button
          type="button"
          onClick={() => void runScan()}
          disabled={scanBusy}
          className="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-50"
        >
          {scanBusy ? 'Scan in corso…' : `Esegui scan Serie A ${DEFAULT_SEASON}`}
        </button>
        <button
          type="button"
          onClick={() => void loadCatalog()}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 shadow-sm"
        >
          Ricarica da cache
        </button>
      </div>

      {catalog?.message ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">{catalog.message}</div>
      ) : null}

      {mode === 'diagnostics' ? (
        <DirectScanDiagnosticsTable diagnostics={diagnostics} />
      ) : null}

      {mode === 'catalog' && catalog ? (
        <>
          <Card title="Riepilogo (ultimo scan)">
            <p className="mb-3 text-xs text-slate-500">
              Conteggi sul catalogo completo. Filtri attivi:{' '}
              <span className="font-semibold text-slate-800">{visibleCount}</span> campi visibili.
            </p>
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <dt className="text-xs font-medium text-slate-500">Campi diretti trovati</dt>
                <dd className="text-lg font-semibold text-slate-900">{s?.direct_fields_found ?? 0}</dd>
              </div>
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <dt className="text-xs font-medium text-slate-500">Endpoint ok (scan)</dt>
                <dd className="text-lg font-semibold text-slate-900">{s?.endpoints_scanned ?? 0}</dd>
              </div>
              <div className="rounded-xl bg-rose-50 px-3 py-2">
                <dt className="text-xs font-medium text-rose-800">Endpoint in errore</dt>
                <dd className="text-lg font-semibold text-rose-950">{s?.endpoints_errors ?? 0}</dd>
              </div>
              <div className="rounded-xl bg-violet-50 px-3 py-2">
                <dt className="text-xs font-medium text-violet-800">Usati da v0.4 (mapping)</dt>
                <dd className="text-lg font-semibold text-violet-950">{s?.fields_used_by_v04 ?? 0}</dd>
              </div>
              <div className="rounded-xl bg-emerald-50 px-3 py-2">
                <dt className="text-xs font-medium text-emerald-800">Salvati in colonna DB</dt>
                <dd className="text-lg font-semibold text-emerald-950">{s?.fields_saved_in_db ?? 0}</dd>
              </div>
              <div className="rounded-xl bg-amber-50 px-3 py-2">
                <dt className="text-xs font-medium text-amber-800">Solo raw_json</dt>
                <dd className="text-lg font-semibold text-amber-950">{s?.fields_raw_json_only ?? 0}</dd>
              </div>
            </dl>
            {catalog.last_scan_at ? (
              <p className="mt-2 text-xs text-slate-500">Ultimo scan: {catalog.last_scan_at}</p>
            ) : null}
          </Card>

          <DirectSelectedFieldsPanel selectedIds={selectedIds} fieldsByStable={fieldsByStable} onClear={clearSel} />

          <DirectCatalogFilters
            search={search}
            onSearchChange={setSearch}
            areaId={areaId}
            onAreaIdChange={setAreaId}
            areaOptions={areaOptions}
            endpoint={endpoint}
            onEndpointChange={setEndpoint}
            dbStatus={dbStatus}
            onDbStatusChange={setDbStatus}
            modelV04={modelV04}
            onModelV04Change={setModelV04}
            sampleType={sampleType}
            onSampleTypeChange={setSampleType}
            onlyV04={onlyV04}
            onOnlyV04Change={setOnlyV04}
            onlyNotSavedDb={onlyNotSavedDb}
            onOnlyNotSavedDbChange={setOnlyNotSavedDb}
            onlyWithTooltip={onlyWithTooltip}
            onOnlyWithTooltipChange={setOnlyWithTooltip}
            onlyNumeric={onlyNumeric}
            onOnlyNumericChange={setOnlyNumeric}
          />

          <div className="space-y-4">
            {catalog.areas.map((area) => {
              const vis = area.parameters.filter((p) => matches(p, filterOpts))
              return (
                <DirectCatalogAreaSection
                  key={area.id}
                  area={area}
                  parameters={vis}
                  open={openMap[area.id] ?? false}
                  onToggle={() => toggleOpen(area.id)}
                  selectedIds={selectedIds}
                  onToggleSelect={toggleSelect}
                />
              )
            })}
          </div>
        </>
      ) : mode === 'catalog' && !catalog && !error ? (
        <p className="text-sm text-slate-600">Caricamento…</p>
      ) : null}
    </div>
  )
}
