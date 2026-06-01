type Props = {
  roundNumber: number
  deleting: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function RoundAnalysisDeleteConfirm({
  roundNumber,
  deleting,
  onCancel,
  onConfirm,
}: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-analysis-title"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="delete-analysis-title" className="text-base font-semibold text-slate-900">
          Elimina analisi
        </h3>
        <p className="mt-2 text-sm text-slate-600">
          Vuoi eliminare l&apos;analisi della Giornata {roundNumber}? Questa operazione rimuoverà i
          risultati salvati di questa analisi.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800"
            disabled={deleting}
            onClick={onCancel}
          >
            Annulla
          </button>
          <button
            type="button"
            className="rounded-lg bg-rose-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            disabled={deleting}
            onClick={onConfirm}
          >
            {deleting ? 'Eliminazione…' : 'Elimina'}
          </button>
        </div>
      </div>
    </div>
  )
}
