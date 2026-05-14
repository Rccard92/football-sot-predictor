import { useCallback, useEffect, useMemo, useState } from 'react'
import { getApiFootballCatalog, type ApiFootballCatalogParameter, type ApiFootballCatalogResponse } from '../lib/api'
import { Card } from '../components/ui/Card'
import { CatalogAreaSection, type AreaHeaderStats } from '../components/catalog/CatalogAreaSection'
import { CatalogFilters } from '../components/catalog/CatalogFilters'
import { SelectedVariablesPanel } from '../components/catalog/SelectedVariablesPanel'

const LS_SELECTED_KEYS = 'apiFootballCatalogSelectedKeys'

function loadSelectedKeysFromStorage(): Set<string> {
  try {
    const raw = localStorage.getItem(LS_SELECTED_KEYS)
    if (!raw) return new Set()
    const arr = JSON.parse(raw) as unknown
    if (!Array.isArray(arr)) return new Set()
    return new Set(arr.filter((x): x is string => typeof x === 'string'))
  } catch {
    return new Set()
  }
}

function persistSelectedKeys(keys: Set<string>) {
  try {
    localStorage.setItem(LS_SELECTED_KEYS, JSON.stringify([...keys]))
  } catch {
    /* ignore */
  }
}

function computeAreaStats(areaParams: ApiFootballCatalogParameter[]): AreaHeaderStats {
  let v04UsedOrIndirect = 0
  let implementedLike = 0
  let toImplementLike = 0
  for (const p of areaParams) {
    if (p.model_v04_status === 'used' || p.model_v04_status === 'indirect') v04UsedOrIndirect += 1
    if (p.implementation_status === 'implemented' || p.implementation_status === 'partial') implementedLike += 1
    if (p.model_v04_status === 'to_implement' || p.implementation_status === 'to_implement') toImplementLike += 1
  }
  return {
    total: areaParams.length,
    v04UsedOrIndirect,
    implementedLike,
    toImplementLike,
  }
}

function matchesFilters(
  p: ApiFootballCatalogParameter,
  opts: {
    q: string
    areaId: string
    endpoint: string
    implementation: string
    modelV04: string
    market: string
  },
): boolean {
  const q = opts.q.trim().toLowerCase()
  if (q) {
    const blob = `${p.name_it} ${p.key} ${p.description_it} ${p.technical_name}`.toLowerCase()
    if (!blob.includes(q)) return false
  }
  if (opts.areaId !== 'all' && p.area_id !== opts.areaId) return false
  if (opts.endpoint.trim()) {
    if (!p.endpoint.toLowerCase().includes(opts.endpoint.trim().toLowerCase())) return false
  }
  if (opts.implementation !== 'all' && p.implementation_status !== opts.implementation) return false
  if (opts.modelV04 !== 'all' && p.model_v04_status !== opts.modelV04) return false
  if (opts.market !== 'all' && !p.useful_markets.includes(opts.market)) return false
  return true
}

export function ApiDataCatalog() {
  const [data, setData] = useState<ApiFootballCatalogResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [areaId, setAreaId] = useState('all')
  const [endpoint, setEndpoint] = useState('')
  const [implementation, setImplementation] = useState('all')
  const [modelV04, setModelV04] = useState('all')
  const [market, setMarket] = useState('all')
  const [openMap, setOpenMap] = useState<Record<string, boolean>>({})
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => loadSelectedKeysFromStorage())

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await getApiFootballCatalog()
        if (cancelled) return
        setData(res)
        setError(null)
        const om: Record<string, boolean> = {}
        for (const a of res.areas) {
          om[a.id] = true
        }
        setOpenMap(om)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Errore caricamento catalogo')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    persistSelectedKeys(selectedKeys)
  }, [selectedKeys])

  const idToName = useMemo(() => {
    const m = new Map<string, string>()
    if (!data) return m
    for (const a of data.areas) {
      for (const p of a.parameters) {
        m.set(p.key, p.name_it)
      }
    }
    return m
  }, [data])

  const areaOptions = useMemo(() => (data ? data.areas.map((a) => ({ id: a.id, title: a.title })) : []), [data])

  const allParams = useMemo(() => {
    if (!data) return []
    return data.areas.flatMap((a) => a.parameters)
  }, [data])

  const marketOptions = useMemo(() => {
    const s = new Set<string>()
    for (const p of allParams) {
      for (const m of p.useful_markets) s.add(m)
    }
    return [...s].sort()
  }, [allParams])

  const filterOpts = useMemo(
    () => ({
      q: search,
      areaId,
      endpoint,
      implementation,
      modelV04,
      market,
    }),
    [search, areaId, endpoint, implementation, modelV04, market],
  )

  const filteredParams = useMemo(
    () => allParams.filter((p) => matchesFilters(p, filterOpts)),
    [allParams, filterOpts],
  )

  const globalSummary = useMemo(() => {
    const total = allParams.length
    let v04Used = 0
    let implNotUsed = 0
    let toImpl = 0
    let apiNo = 0
    for (const p of allParams) {
      if (p.model_v04_status === 'used' || p.model_v04_status === 'indirect') v04Used += 1
      if (p.model_v04_status === 'implemented_not_used') implNotUsed += 1
      if (p.model_v04_status === 'to_implement' || p.implementation_status === 'to_implement') toImpl += 1
      if (p.api_status === 'not_in_provider' || p.api_status === 'external_provider') apiNo += 1
    }
    return { total, v04Used, implNotUsed, toImpl, apiNo }
  }, [allParams])

  const visibleCount = filteredParams.length

  const toggleOpen = useCallback((id: string) => {
    setOpenMap((prev) => ({ ...prev, [id]: !prev[id] }))
  }, [])

  const toggleSelect = useCallback((key: string) => {
    setSelectedKeys((prev) => {
      const n = new Set(prev)
      if (n.has(key)) n.delete(key)
      else n.add(key)
      return n
    })
  }, [])

  const clearSelection = useCallback(() => setSelectedKeys(new Set()), [])

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Catalogo dati API</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Panoramica dei parametri disponibili da API-Football, con stato di utilizzo nel modello v0.4.
        </p>
      </header>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">{error}</div>
      ) : null}

      <Card title="Riepilogo">
        <p className="mb-3 text-xs text-slate-500">
          I conteggi seguenti si riferiscono al catalogo completo (69 parametri), indipendentemente dai filtri. Con i
          filtri attivi sono visibili <span className="font-semibold text-slate-800">{visibleCount}</span> parametri.
        </p>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-xl bg-slate-50 px-3 py-2">
            <dt className="text-xs font-medium text-slate-500">Parametri totali censiti</dt>
            <dd className="text-lg font-semibold text-slate-900">{globalSummary.total}</dd>
          </div>
          <div className="rounded-xl bg-emerald-50 px-3 py-2">
            <dt className="text-xs font-medium text-emerald-800">Già usati in v0.4 (diretto o indiretto)</dt>
            <dd className="text-lg font-semibold text-emerald-950">{globalSummary.v04Used}</dd>
          </div>
          <div className="rounded-xl bg-violet-50 px-3 py-2">
            <dt className="text-xs font-medium text-violet-800">Implementati ma non usati (modello)</dt>
            <dd className="text-lg font-semibold text-violet-950">{globalSummary.implNotUsed}</dd>
          </div>
          <div className="rounded-xl bg-amber-50 px-3 py-2">
            <dt className="text-xs font-medium text-amber-800">Da implementare (stato progetto o modello)</dt>
            <dd className="text-lg font-semibold text-amber-950">{globalSummary.toImpl}</dd>
          </div>
          <div className="rounded-xl bg-rose-50 px-3 py-2">
            <dt className="text-xs font-medium text-rose-800">Non disponibili nel provider attuale</dt>
            <dd className="text-lg font-semibold text-rose-950">{globalSummary.apiNo}</dd>
          </div>
          <div className="rounded-xl bg-slate-100 px-3 py-2">
            <dt className="text-xs font-medium text-slate-600">Parametri selezionati dall&apos;utente</dt>
            <dd className="text-lg font-semibold text-slate-900">{selectedKeys.size}</dd>
          </div>
        </dl>
      </Card>

      <SelectedVariablesPanel selectedKeys={[...selectedKeys]} idToName={idToName} onClear={clearSelection} />

      {data ? (
        <>
          <CatalogFilters
            search={search}
            onSearchChange={setSearch}
            areaId={areaId}
            onAreaIdChange={setAreaId}
            areaOptions={areaOptions}
            endpoint={endpoint}
            onEndpointChange={setEndpoint}
            implementation={implementation}
            onImplementationChange={setImplementation}
            modelV04={modelV04}
            onModelV04Change={setModelV04}
            market={market}
            onMarketChange={setMarket}
            marketOptions={marketOptions}
          />

          <div className="space-y-4">
            {data.areas.map((area) => {
              const visible = area.parameters.filter((p) => matchesFilters(p, filterOpts))
              const stats = computeAreaStats(area.parameters)
              return (
                <CatalogAreaSection
                  key={area.id}
                  area={area}
                  stats={stats}
                  parameters={visible}
                  open={openMap[area.id] ?? false}
                  onToggle={() => toggleOpen(area.id)}
                  selectedKeys={selectedKeys}
                  onToggleSelect={toggleSelect}
                />
              )
            })}
          </div>
        </>
      ) : !error ? (
        <p className="text-sm text-slate-600">Caricamento catalogo…</p>
      ) : null}
    </div>
  )
}
