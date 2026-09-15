type Props = {
  isScanned: boolean
  scanDayLoading: boolean
  scanInProgress?: boolean
  updateResultsLoading: boolean
  onScanDay: (forceRescan: boolean) => void
  onUpdateResults: () => void
}

export function CecchinoTodayPageHeader({
  isScanned,
  scanDayLoading,
  scanInProgress = false,
  updateResultsLoading,
  onScanDay,
  onUpdateResults,
}: Props) {
  const scanBusy = scanDayLoading || scanInProgress

  return (
    <header className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Cecchino Today</h1>

      <div className="flex flex-wrap gap-3">
        {!isScanned ? (
          <button
            type="button"
            onClick={() => onScanDay(false)}
            disabled={scanBusy}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {scanBusy ? 'Scansione in corso…' : 'Avvia scansione giornata'}
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onUpdateResults()}
              disabled={updateResultsLoading || scanBusy}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {updateResultsLoading ? 'Aggiornamento…' : 'Aggiorna risultati giornata'}
            </button>
            <button
              type="button"
              onClick={() => onScanDay(true)}
              disabled={scanBusy}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {scanBusy ? 'Scansione in corso…' : 'Riscansiona giornata'}
            </button>
          </>
        )}
      </div>
    </header>
  )
}
