type SelectedVariablesPanelProps = {
  selectedKeys: string[]
  idToName: Map<string, string>
  onClear: () => void
}

export function SelectedVariablesPanel({ selectedKeys, idToName, onClear }: SelectedVariablesPanelProps) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Variabili selezionate</h2>
          <p className="mt-1 text-xs text-slate-500">
            Salvate in questo browser (localStorage). Non influenzano il modello in questa versione.
          </p>
          <p className="mt-2 text-sm font-medium text-slate-800">
            {selectedKeys.length} selezionat{selectedKeys.length === 1 ? 'a' : 'e'}
          </p>
          {selectedKeys.length > 0 ? (
            <ul className="mt-2 max-h-40 list-inside list-disc overflow-y-auto text-sm text-slate-700">
              {selectedKeys.map((k) => (
                <li key={k}>{idToName.get(k) ?? k}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate-500">Nessuna variabile selezionata.</p>
          )}
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:items-end">
          <button
            type="button"
            onClick={onClear}
            disabled={selectedKeys.length === 0}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Svuota selezione
          </button>
          <button
            type="button"
            disabled
            title="Funzione pianificata: in futuro esporterà un set di variabili candidate per il modello, senza modificare automaticamente i pesi."
            className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white opacity-40 shadow-sm"
          >
            Crea set variabili modello
          </button>
        </div>
      </div>
    </div>
  )
}
