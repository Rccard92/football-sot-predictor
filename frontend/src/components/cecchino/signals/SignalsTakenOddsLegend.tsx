export function SignalsTakenOddsLegend() {
  return (
    <details className="rounded-lg border border-slate-200 bg-white text-sm">
      <summary className="cursor-pointer px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
        Come leggere Quota Prese e Quota Void
      </summary>
      <div className="border-t border-slate-200 px-4 py-3 space-y-2 text-xs text-slate-600">
        <p>
          La Quota media prese considera solo le quote dei segnali che sono andati a buon fine. Se un
          segnale si accende ma perde, la sua quota non entra in questa media. La Quota Void indica
          invece la quota minima necessaria per andare in pareggio in base al Win Rate. Quando la
          Quota media prese supera la Quota Void, il segnale mostra una qualità interessante.
        </p>
        <p className="text-slate-500">
          Questa metrica non rappresenta il ROI reale completo, ma una misura della qualità delle
          partite effettivamente prese dal segnale.
        </p>
      </div>
    </details>
  )
}
