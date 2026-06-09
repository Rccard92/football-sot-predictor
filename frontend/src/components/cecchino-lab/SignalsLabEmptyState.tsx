type Props = {
  variant: 'no_fixtures' | 'no_models'
  onBacktest?: () => void
  actionLoading?: boolean
}

export function SignalsLabEmptyState({ variant, onBacktest, actionLoading }: Props) {
  if (variant === 'no_fixtures') {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 px-6 py-10 text-center">
        <p className="text-sm font-medium text-slate-700">Nessun dato nel periodo selezionato</p>
        <p className="mt-1 text-xs text-slate-500">Modifica le date o sincronizza i segnali dalla pagina stabile.</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-amber-200/80 bg-amber-50/50 px-6 py-8 text-center">
      <p className="text-sm font-medium text-amber-900">
        Per questo intervallo non esiste ancora il backtest dei modelli.
      </p>
      <p className="mt-1 text-xs text-amber-800">Clicca Ricalcola modelli A–F per generare i dati comparativi.</p>
      {onBacktest && (
        <button
          type="button"
          onClick={onBacktest}
          disabled={actionLoading}
          className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {actionLoading ? 'Elaborazione…' : 'Calcola modelli A–F'}
        </button>
      )}
    </div>
  )
}
