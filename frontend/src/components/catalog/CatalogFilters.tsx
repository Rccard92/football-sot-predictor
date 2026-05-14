import { labelMarket } from './statusLabels'

type CatalogFiltersProps = {
  search: string
  onSearchChange: (v: string) => void
  areaId: string
  onAreaIdChange: (v: string) => void
  areaOptions: { id: string; title: string }[]
  endpoint: string
  onEndpointChange: (v: string) => void
  implementation: string
  onImplementationChange: (v: string) => void
  modelV04: string
  onModelV04Change: (v: string) => void
  market: string
  onMarketChange: (v: string) => void
  marketOptions: string[]
}

export function CatalogFilters({
  search,
  onSearchChange,
  areaId,
  onAreaIdChange,
  areaOptions,
  endpoint,
  onEndpointChange,
  implementation,
  onImplementationChange,
  modelV04,
  onModelV04Change,
  market,
  onMarketChange,
  marketOptions,
}: CatalogFiltersProps) {
  const inputCls =
    'mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-300'

  return (
    <div className="sticky top-0 z-10 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Filtri</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <label className="block text-xs font-medium text-slate-600 xl:col-span-2">
          Cerca parametro
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Nome, chiave o descrizione…"
            className={inputCls}
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Area dati
          <select value={areaId} onChange={(e) => onAreaIdChange(e.target.value)} className={inputCls}>
            <option value="all">Tutte le aree</option>
            {areaOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {a.title}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Endpoint / API
          <input
            value={endpoint}
            onChange={(e) => onEndpointChange(e.target.value)}
            placeholder="es. fixtures/statistics"
            className={inputCls}
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Stato nel progetto
          <select value={implementation} onChange={(e) => onImplementationChange(e.target.value)} className={inputCls}>
            <option value="all">Tutti</option>
            <option value="implemented">Implementato</option>
            <option value="partial">Parzialmente implementato</option>
            <option value="to_implement">Da implementare</option>
            <option value="to_verify">Da verificare</option>
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Stato modello v0.4
          <select value={modelV04} onChange={(e) => onModelV04Change(e.target.value)} className={inputCls}>
            <option value="all">Tutti</option>
            <option value="used">Usato</option>
            <option value="indirect">Usato indirettamente</option>
            <option value="implemented_not_used">Implementato, non usato</option>
            <option value="to_implement">Da implementare</option>
            <option value="not_available">Non disponibile</option>
            <option value="verify">Da verificare</option>
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Mercato utile
          <select value={market} onChange={(e) => onMarketChange(e.target.value)} className={inputCls}>
            <option value="all">Tutti i mercati</option>
            {marketOptions.map((mk) => (
              <option key={mk} value={mk}>
                {labelMarket(mk)}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  )
}
