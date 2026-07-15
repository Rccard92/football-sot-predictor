type Props = {
  temporal: Record<string, unknown>
}

export function DrawCredibilityTemporalStabilityPanel({ temporal }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Stabilità temporale</h3>
      <div className="grid gap-2 text-sm text-slate-700 sm:grid-cols-2">
        <p>
          <span className="font-medium">Finestra osservazione:</span>{' '}
          {String(temporal.time_span_days ?? '—')} giorni
        </p>
        <p>
          <span className="font-medium">Finestra breve:</span>{' '}
          {temporal.short_observation_window ? 'Sì' : 'No'}
        </p>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Analisi per settimana ISO e terzili kickoff disponibile quando il periodo copre più bucket
        significativi.
      </p>
    </section>
  )
}
