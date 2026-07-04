type Props = {
  variant: 'no_fixtures' | 'not_synced' | 'no_rating'
  onSync?: () => void
  actionLoading?: boolean
}

export function KpiSignalsEmptyState({ variant, onSync, actionLoading }: Props) {
  const messages = {
    no_fixtures: {
      title: 'Nessuna partita Cecchino nel periodo',
      body: 'Modifica le date o attendi una scansione Cecchino Today per la giornata selezionata.',
      tone: 'slate' as const,
    },
    not_synced: {
      title: 'Segnali KPI non ancora sincronizzati',
      body: 'Ci sono partite con Pannello KPI, ma le activation KPI non sono state generate per questo intervallo.',
      tone: 'cyan' as const,
    },
    no_rating: {
      title: 'Nessuna riga KPI con rating ≥ 50',
      body: 'Nel periodo selezionato non ci sono righe Pannello KPI con quota book e rating sufficiente.',
      tone: 'amber' as const,
    },
  }
  const msg = messages[variant]
  const border =
    msg.tone === 'cyan'
      ? 'border-cyan-200/80 bg-gradient-to-br from-cyan-50/50 to-white'
      : msg.tone === 'amber'
        ? 'border-amber-200/80 bg-gradient-to-br from-amber-50/50 to-white'
        : 'border-dashed border-slate-300 bg-white/60'

  return (
    <div className={`rounded-2xl border px-6 py-10 text-center shadow-sm ${border}`}>
      <p className="text-sm font-semibold text-slate-800">{msg.title}</p>
      <p className="mt-2 text-xs leading-relaxed text-slate-500">{msg.body}</p>
      {variant === 'not_synced' && onSync ? (
        <button
          type="button"
          disabled={actionLoading}
          onClick={onSync}
          className="mt-5 rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-800 disabled:opacity-50"
        >
          {actionLoading ? 'Sincronizzazione…' : 'Sincronizza KPI'}
        </button>
      ) : null}
    </div>
  )
}
