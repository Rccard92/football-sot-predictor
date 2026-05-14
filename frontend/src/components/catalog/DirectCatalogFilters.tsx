type Props = {
  search: string
  onSearchChange: (v: string) => void
  areaId: string
  onAreaIdChange: (v: string) => void
  areaOptions: { id: string; title: string }[]
  endpoint: string
  onEndpointChange: (v: string) => void
  dbStatus: string
  onDbStatusChange: (v: string) => void
  modelV04: string
  onModelV04Change: (v: string) => void
  sampleType: string
  onSampleTypeChange: (v: string) => void
  onlyV04: boolean
  onOnlyV04Change: (v: boolean) => void
  onlyNotSavedDb: boolean
  onOnlyNotSavedDbChange: (v: boolean) => void
  onlyWithTooltip: boolean
  onOnlyWithTooltipChange: (v: boolean) => void
  onlyNumeric: boolean
  onOnlyNumericChange: (v: boolean) => void
}

const inputCls =
  'mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-300'

export function DirectCatalogFilters(props: Props) {
  return (
    <div className="sticky top-0 z-10 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Filtri</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <label className="block text-xs font-medium text-slate-600 xl:col-span-2">
          Cerca campo
          <input
            type="search"
            value={props.search}
            onChange={(e) => props.onSearchChange(e.target.value)}
            placeholder="Nome, path, endpoint…"
            className={inputCls}
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Area
          <select value={props.areaId} onChange={(e) => props.onAreaIdChange(e.target.value)} className={inputCls}>
            <option value="all">Tutte</option>
            {props.areaOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {a.title}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Endpoint
          <input value={props.endpoint} onChange={(e) => props.onEndpointChange(e.target.value)} className={inputCls} />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Stato DB
          <select value={props.dbStatus} onChange={(e) => props.onDbStatusChange(e.target.value)} className={inputCls}>
            <option value="all">Tutti</option>
            <option value="saved_column">Salvato in colonna</option>
            <option value="raw_json_only">Solo raw_json</option>
            <option value="not_saved">Non salvato</option>
            <option value="unknown">Sconosciuto</option>
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Stato modello v0.4
          <select value={props.modelV04} onChange={(e) => props.onModelV04Change(e.target.value)} className={inputCls}>
            <option value="all">Tutti</option>
            <option value="used_v04">Usato da v0.4</option>
            <option value="not_used_v04">Non usato</option>
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Tipo dato
          <select value={props.sampleType} onChange={(e) => props.onSampleTypeChange(e.target.value)} className={inputCls}>
            <option value="all">Tutti</option>
            <option value="stringa">stringa</option>
            <option value="numero">numero</option>
            <option value="percentuale">percentuale</option>
            <option value="boolean">boolean</option>
            <option value="data">data</option>
            <option value="null">null</option>
          </select>
        </label>
      </div>
      <div className="mt-3 flex flex-wrap gap-4 border-t border-slate-100 pt-3 text-sm text-slate-700">
        <label className="inline-flex cursor-pointer items-center gap-2">
          <input type="checkbox" checked={props.onlyV04} onChange={(e) => props.onOnlyV04Change(e.target.checked)} />
          Solo campi usati da v0.4
        </label>
        <label className="inline-flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={props.onlyNotSavedDb}
            onChange={(e) => props.onOnlyNotSavedDbChange(e.target.checked)}
          />
          Solo non salvati in DB
        </label>
        <label className="inline-flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={props.onlyWithTooltip}
            onChange={(e) => props.onOnlyWithTooltipChange(e.target.checked)}
          />
          Solo con tooltip
        </label>
        <label className="inline-flex cursor-pointer items-center gap-2">
          <input type="checkbox" checked={props.onlyNumeric} onChange={(e) => props.onOnlyNumericChange(e.target.checked)} />
          Solo numerici
        </label>
      </div>
    </div>
  )
}
