import { useState } from 'react'

export function KpiSignalsInfoPanel() {
  const [open, setOpen] = useState(false)

  return (
    <section className="rounded-2xl border border-cyan-100 bg-gradient-to-br from-cyan-50/50 via-white to-teal-50/30 p-5 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <h2 className="text-sm font-semibold text-slate-800">Come leggere Segnali KPI</h2>
        <span className="text-slate-400">{open ? '−' : '+'}</span>
      </button>
      {open ? (
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-600">
          <li>Ogni riga KPI con quota book e rating ≥ 50 genera un segnale.</li>
          <li>Lo stake è fisso a 1 unità.</li>
          <li>Se il pronostico vince, il profitto è quota_book − 1.</li>
          <li>Se perde, il profitto è −1.</li>
          <li>ROI = profitto / segnali valutati.</li>
          <li>Quota void = 1 / win rate (informativa).</li>
          <li>Nessuna chiamata API: usa solo dati già presenti nel database.</li>
        </ul>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          Clicca per espandere la legenda operativa su stake, profitto, ROI e quota void.
        </p>
      )}
    </section>
  )
}
