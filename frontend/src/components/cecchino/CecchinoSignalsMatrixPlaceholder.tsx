type Props = {
  status?: string
}

export function CecchinoSignalsMatrixPlaceholder({ status = 'insufficient_data' }: Props) {
  const message =
    status === 'insufficient_data'
      ? 'Dati insufficienti per calcolare la matrice segnali SI/NO (quote finali 1/X/2 non disponibili).'
      : `Matrice segnali non disponibile (stato: ${status ?? '—'}).`

  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4">
      <h3 className="text-sm font-semibold text-slate-800">Segnali Cecchino (matrice SI/NO)</h3>
      <p className="mt-2 text-xs text-slate-600">{message}</p>
    </div>
  )
}
