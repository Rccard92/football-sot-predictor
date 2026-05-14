const inputCls =
  'mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-300'

type AreaOpt = { id: string; title: string }

type Props = {
  search: string
  onSearchChange: (v: string) => void
  areaId: string
  onAreaIdChange: (v: string) => void
  areaOptions: AreaOpt[]
  endpoint: string
  onEndpointChange: (v: string) => void
  classification: string
  onClassificationChange: (v: string) => void
  classificationOptions: string[]
  priority: string
  onPriorityChange: (v: string) => void
  dbStatus: string
  onDbStatusChange: (v: string) => void
  modelV04: string
  onModelV04Change: (v: string) => void
  sampleType: string
  onSampleTypeChange: (v: string) => void
  onlyV04: boolean
  onOnlyV04Change: (v: boolean) => void
}

export function ModelRelevantFilters(props: Props) {
  return (
    <div className="sticky top-0 z-10 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm backdrop-blur">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Filtri</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <label className="block text-xs font-medium text-slate-600 xl:col-span-2">
          Cerca
          <input
            type="search"
            value={props.search}
            onChange={(e) => props.onSearchChange(e.target.value)}
            placeholder="Nome, path, endpoint, motivo…"
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
          Categoria
          <select
            value={props.classification}
            onChange={(e) => props.onClassificationChange(e.target.value)}
            className={inputCls}
          >
            <option value="all">Tutte</option>
            {props.classificationOptions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Priorità
          <select value={props.priority} onChange={(e) => props.onPriorityChange(e.target.value)} className={inputCls}>
            <option value="all">Tutte</option>
            <option value="A">A</option>
            <option value="B">B</option>
            <option value="C">C</option>
          </select>
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
      <div className="mt-3 border-t border-slate-100 pt-3">
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={props.onlyV04} onChange={(e) => props.onOnlyV04Change(e.target.checked)} />
          Solo campi usati da v0.4
        </label>
      </div>
    </div>
  )
}
