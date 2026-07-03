type Props = {
  variant: 'no_fixtures' | 'not_synced' | 'no_rating' | null
  onSync?: () => void
}

export function KpiSignalsEmptyState({ variant, onSync }: Props) {
  if (!variant) return null
  const messages = {
    no_fixtures: 'Nessuna partita Cecchino nel periodo selezionato.',
    not_synced:
      'Ci sono partite Cecchino nel periodo, ma i Segnali KPI non sono ancora stati sincronizzati.',
    no_rating: 'Nessuna riga KPI con rating almeno 50 nel periodo selezionato.',
  }
  return (
    <section className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center shadow-sm">
      <p className="text-sm text-slate-600">{messages[variant]}</p>
      {variant === 'not_synced' && onSync ? (
        <button type="button" className="mt-4 rounded-lg bg-cyan-700 px-4 py-2 text-sm text-white" onClick={onSync}>
          Sincronizza KPI
        </button>
      ) : null}
    </section>
  )
}

export function KpiSignalsSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-24 rounded-2xl bg-slate-200" />
      <div className="h-40 rounded-2xl bg-slate-200" />
      <div className="h-64 rounded-2xl bg-slate-200" />
    </div>
  )
}

export function KpiSignalsInfoPanel() {
  return (
    <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
      <h3 className="font-semibold text-slate-800">Come leggere Segnali KPI</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>Ogni riga KPI con quota book e rating ≥ 50 genera un segnale.</li>
        <li>Stake fisso 1: profitto = quota − 1 se vinto, −1 se perso.</li>
        <li>ROI = profitto totale / segnali valutati × 100.</li>
        <li>Quota void = 1 / win rate (informativa).</li>
        <li>Nessuna chiamata API: solo dati già presenti nel database.</li>
      </ul>
    </section>
  )
}
