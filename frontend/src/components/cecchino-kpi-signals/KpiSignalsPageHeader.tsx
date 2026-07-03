export function KpiSignalsPageHeader() {
  return (
    <header className="rounded-2xl border border-cyan-100/80 bg-gradient-to-r from-white via-cyan-50/40 to-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-cyan-700">Cecchino</p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">Segnali KPI</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Analisi delle quote di valore individuate dal Pannello KPI Cecchino, divise per rating e
            valutate con stake fisso 1.
          </p>
        </div>
        <span className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-medium text-cyan-800">
          Modulo separato · Dati DB
        </span>
      </div>
    </header>
  )
}
