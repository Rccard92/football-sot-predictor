import { SIGNAL_LAB_FILTER_NOTE } from '../cecchino/signalMinBookOdds'

export function SignalsLabInfoPanel() {
  return (
    <section className="rounded-2xl border border-cyan-100 bg-gradient-to-br from-cyan-50/50 via-white to-indigo-50/30 p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-800">Quota Prese, Quota Void e Rendimento</h2>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{SIGNAL_LAB_FILTER_NOTE}</p>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">
        Un segnale tecnico SI senza valore quota o sotto soglia minima operativa è escluso anche se
        poi risultasse vincente.
      </p>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">
        X PT misura il pareggio a primo tempo con quote reali book e Cecchino dal Pannello KPI. Nel
        monitoraggio viene creato solo quando la X finale era segnale a valore e anche X PT passa
        filtro valore e soglia minima configurata.
      </p>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">
        La Quota media prese considera solo le quote dei segnali vinti. La Quota Void indica la quota
        minima di pareggio rispetto al Win Rate. Quando la quota media prese supera la quota void, il
        segnale mostra una qualità interessante.
      </p>
      <div className="mt-4 rounded-xl bg-white/80 px-4 py-3 ring-1 ring-slate-200/60">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Formula sintetica</p>
        <p className="mt-1 text-sm font-medium text-indigo-900">
          Rendimento prese = Win Rate × Quota media prese − 1
        </p>
      </div>
    </section>
  )
}
