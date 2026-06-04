type Props = {
  status?: string
}

export function CecchinoOddsComparisonPlaceholder({ status = 'not_implemented_yet' }: Props) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4">
      <h3 className="text-sm font-semibold text-slate-800">Confronto quota matematica vs bookmaker</h3>
      <p className="mt-2 text-xs text-slate-600">
        Il confronto tra quota matematica Cecchino e quote bookmaker è in attesa di integrazione con i
        dati SportAPI/bookmaker (come per la sezione Bookmakers admin). Stato backend:{' '}
        <span className="font-medium text-slate-800">{status}</span> — nessun confronto viene mostrato
        in questa versione.
      </p>
    </div>
  )
}
