type Props = {
  status?: string
}

export function CecchinoSignalsMatrixPlaceholder({ status = 'pending_formula_extraction' }: Props) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4">
      <h3 className="text-sm font-semibold text-slate-800">Segnali Cecchino (matrice SI/NO)</h3>
      <p className="mt-2 text-xs text-slate-600">
        Sezione in attesa di estrazione formula da Excel. Stato:{' '}
        <span className="font-medium text-slate-800">{status}</span>
      </p>
    </div>
  )
}
