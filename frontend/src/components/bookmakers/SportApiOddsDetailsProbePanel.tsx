export function SportApiOddsDetailsProbePanel() {
  return (
    <section className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-800">Test endpoint alternativi</h2>
      <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
        Endpoint <span className="font-mono">odds_details</span> presente in RapidAPI ma non ancora
        mappato: servono parametri esatti (path, query, body) prima di abilitare una chiamata reale.
      </p>
      <button
        type="button"
        disabled
        className="mt-3 cursor-not-allowed rounded-md border border-slate-300 bg-slate-100 px-3 py-1.5 text-[11px] text-slate-500"
        title="In attesa di mapping parametri RapidAPI"
      >
        Non ancora mappato
      </button>
    </section>
  )
}
