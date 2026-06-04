type Props = {
  status?: string
}

export function CecchinoSignalsMatrixPlaceholder({ status = 'pending_formula_extraction' }: Props) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4">
      <h3 className="text-sm font-semibold text-slate-800">Segnali Cecchino (matrice SI/NO)</h3>
      <p className="mt-2 text-xs text-slate-600">
        La matrice segnali SI/NO del foglio Excel CECCHINO non è ancora disponibile online: le formule
        devono essere estratte da AutomazioneCecchino.xlsm. In questa versione il backend espone solo
        lo stato <span className="font-medium text-slate-800">{status}</span> — nessun segnale SI/NO
        viene calcolato né mostrato.
      </p>
    </div>
  )
}
